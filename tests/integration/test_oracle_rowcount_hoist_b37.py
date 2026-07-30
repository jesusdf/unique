# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""B37 — Oracle ``SQL%ROWCOUNT`` used in EXPRESSION position → PostgreSQL.

PostgreSQL's ``ROW_COUNT`` is readable only through ``GET DIAGNOSTICS``, a
*statement*, so it cannot be substituted inline into ``IF SQL%ROWCOUNT <> 1``
or ``v := SQL%ROWCOUNT + 1``. The transformer hoists a
``GET DIAGNOSTICS uq_rowcount = ROW_COUNT;`` immediately before the
referencing statement and substitutes the declared local ``uq_rowcount`` in
the expression. A re-evaluated loop/exit condition cannot be captured once, so
it degrades honestly with the existing UNIQUE-1033 carrier.

T-SQL (``@@ROWCOUNT``) and MySQL (``ROW_COUNT()``) already read the implicit
row count inline, so those targets are left untouched (covered here as a
regression guard).
"""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler


def _t(src: str, target: str = "postgresql") -> object:
    return Transpiler().transpile(src, "oracle", target)


def _flat(sql: str) -> str:
    return " ".join(sql.split())


_IF_ROWCOUNT = (
    "CREATE OR REPLACE PROCEDURE p IS\n"
    "BEGIN\n"
    "    UPDATE t SET x = 1 WHERE id = 5;\n"
    "    IF SQL%ROWCOUNT <> 1 THEN\n"
    "        RAISE_APPLICATION_ERROR(-20001, 42);\n"
    "    END IF;\n"
    "END;\n/"
)


class TestIfCondition:
    def test_get_diagnostics_hoisted_before_if(self) -> None:
        out = _t(_IF_ROWCOUNT).sql
        flat = _flat(out)
        # Target idiom appeared: a GET DIAGNOSTICS captures ROW_COUNT.
        assert "GET DIAGNOSTICS uq_rowcount = ROW_COUNT;" in flat, out
        # The expression now reads the captured local, not the pseudo-column.
        assert "IF uq_rowcount <> 1 THEN" in flat, out
        # Source idiom and the degrade carrier are both gone.
        assert "SQL%ROWCOUNT" not in out.upper().replace(" ", "")
        assert "%ROWCOUNT" not in out.upper()
        assert "UNIQUE-1033" not in out, out

    def test_capture_point_between_dml_and_use(self) -> None:
        out = _flat(_t(_IF_ROWCOUNT).sql)
        upd = out.index("UPDATE t")
        cap = out.index("GET DIAGNOSTICS uq_rowcount")
        use = out.index("IF uq_rowcount")
        # Hoisted right after the DML it reads and right before the use.
        assert upd < cap < use, out

    def test_temp_local_declared_once(self) -> None:
        out = _t(_IF_ROWCOUNT).sql
        assert re.search(r"(?i)\buq_rowcount\s+bigint\b", out), out
        # Exactly one declaration, no matter how many references.
        assert len(re.findall(r"(?i)\buq_rowcount\s+bigint\b", out)) == 1, out

    def test_no_lossy_warning_when_hoisted(self) -> None:
        result = _t(_IF_ROWCOUNT)
        codes = [w.code for w in result.warnings]
        assert "UNIQUE-1033" not in codes, codes


class TestArithmeticAndAssignment:
    def test_arithmetic_expression(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p IS\n"
            "    v NUMBER;\n"
            "BEGIN\n"
            "    UPDATE t SET x = 1 WHERE id = 5;\n"
            "    v := SQL%ROWCOUNT + 1;\n"
            "END;\n/"
        )
        out = _flat(_t(src).sql)
        assert "GET DIAGNOSTICS uq_rowcount = ROW_COUNT;" in out, out
        assert "v := uq_rowcount + 1;" in out, out
        assert "UNIQUE-1033" not in out, out

    def test_standalone_assignment(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p IS\n"
            "    v NUMBER;\n"
            "BEGIN\n"
            "    UPDATE t SET x = 1 WHERE id = 5;\n"
            "    v := SQL%ROWCOUNT;\n"
            "END;\n/"
        )
        out = _flat(_t(src).sql)
        assert "GET DIAGNOSTICS uq_rowcount = ROW_COUNT;" in out, out
        assert "v := uq_rowcount;" in out, out
        assert "UNIQUE-1033" not in out, out


class TestNestedCallArgument:
    def test_call_argument(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p IS\n"
            "BEGIN\n"
            "    DELETE FROM t WHERE id = 5;\n"
            "    log_rows(SQL%ROWCOUNT);\n"
            "END;\n/"
        )
        out = _flat(_t(src).sql)
        assert "GET DIAGNOSTICS uq_rowcount = ROW_COUNT;" in out, out
        assert "uq_rowcount" in out.split("GET DIAGNOSTICS")[1], out
        assert "UNIQUE-1033" not in out, out


class TestFunctionReturn:
    def test_return_expression(self) -> None:
        src = (
            "CREATE OR REPLACE FUNCTION f RETURN NUMBER IS\n"
            "BEGIN\n"
            "    UPDATE t SET x = 1 WHERE id = 5;\n"
            "    RETURN SQL%ROWCOUNT;\n"
            "END;\n/"
        )
        out = _flat(_t(src).sql)
        assert "GET DIAGNOSTICS uq_rowcount = ROW_COUNT;" in out, out
        assert "RETURN uq_rowcount;" in out, out
        assert "UNIQUE-1033" not in out, out


class TestMultipleReferences:
    def test_two_ifs_share_one_declare(self) -> None:
        src = (
            "CREATE OR REPLACE PROCEDURE p IS\n"
            "BEGIN\n"
            "    UPDATE t SET x = 1 WHERE id = 5;\n"
            "    IF SQL%ROWCOUNT <> 1 THEN\n"
            "        RAISE_APPLICATION_ERROR(-20001, 42);\n"
            "    END IF;\n"
            "    DELETE FROM t WHERE id = 6;\n"
            "    IF SQL%ROWCOUNT = 0 THEN\n"
            "        RAISE_APPLICATION_ERROR(-20001, 43);\n"
            "    END IF;\n"
            "END;\n/"
        )
        out = _t(src).sql
        flat = _flat(out)
        # One declaration, two independent captures (one per DML).
        assert len(re.findall(r"(?i)\buq_rowcount\s+bigint\b", out)) == 1, out
        assert flat.count("GET DIAGNOSTICS uq_rowcount = ROW_COUNT;") == 2, out
        assert "UNIQUE-1033" not in out, out


class TestLoopConditionDegrades:
    def test_while_condition_kept_as_carrier(self) -> None:
        # A WHILE condition is re-evaluated each iteration; a single hoist
        # cannot capture it faithfully, so it must degrade honestly.
        src = (
            "CREATE OR REPLACE PROCEDURE p IS\n"
            "BEGIN\n"
            "    WHILE SQL%ROWCOUNT > 0 LOOP\n"
            "        DELETE FROM t WHERE flag = 1;\n"
            "    END LOOP;\n"
            "END;\n/"
        )
        result = _t(src)
        assert "UNIQUE-1033" in result.sql, result.sql
        assert "UNIQUE-1033" in [w.code for w in result.warnings], result.warnings
        # It must NOT silently invent a frozen capture for the loop condition.
        assert "GET DIAGNOSTICS uq_rowcount" not in result.sql, result.sql

    def test_rowcount_inside_loop_body_is_hoisted(self) -> None:
        # A reference in the loop BODY re-captures each iteration correctly:
        # the GET DIAGNOSTICS lives inside the loop, before the use.
        src = (
            "CREATE OR REPLACE PROCEDURE p IS\n"
            "    v NUMBER;\n"
            "BEGIN\n"
            "    LOOP\n"
            "        DELETE FROM t WHERE flag = 1;\n"
            "        v := SQL%ROWCOUNT;\n"
            "        EXIT WHEN v = 0;\n"
            "    END LOOP;\n"
            "END;\n/"
        )
        out = _flat(_t(src).sql)
        assert "GET DIAGNOSTICS uq_rowcount = ROW_COUNT;" in out, out
        assert "v := uq_rowcount;" in out, out
        # Capture is inside the loop, after the DELETE.
        loop = out.index("LOOP")
        cap = out.index("GET DIAGNOSTICS uq_rowcount")
        assert loop < cap, out
        assert "UNIQUE-1033" not in out, out


class TestOtherTargetsUnchanged:
    def test_tsql_reads_rowcount_inline(self) -> None:
        out = _flat(_t(_IF_ROWCOUNT, "tsql").sql)
        assert "IF @@ROWCOUNT <> 1" in out, out
        assert "GET DIAGNOSTICS" not in out, out
        assert "UNIQUE-1033" not in out, out

    def test_mysql_reads_rowcount_inline(self) -> None:
        out = _flat(_t(_IF_ROWCOUNT, "mysql").sql)
        assert "ROW_COUNT()" in out, out
        assert "GET DIAGNOSTICS uq_rowcount" not in out, out
        assert "UNIQUE-1033" not in out, out
