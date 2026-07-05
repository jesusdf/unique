"""Regression tests for the function/type mappings the corpus sweep surfaced.

Each was an engine-specific gap (a function or CAST type with no faithful target
form) annotated ``-- @xfail`` until fixed. Pinned here as fast unit tests that
also assert the output is valid SQL for the target.
"""

import pytest
import sqlglot

from unique.core.transpiler import Transpiler

_READ = {"tsql": "tsql", "postgresql": "postgres", "mysql": "mysql", "oracle": "oracle"}


def _valid(sql: str, dialect: str) -> None:
    sqlglot.parse(sql, read=_READ[dialect], error_level=sqlglot.ErrorLevel.RAISE)


t = Transpiler()


def _run(sql: str, source: str, target: str) -> str:
    out = t.transpile(sql, source, target).sql
    _valid(out, target)
    return out.upper()


class TestNullFunctions:
    @pytest.mark.parametrize("target", ["mysql", "postgresql", "tsql"])
    def test_nvl2_to_case(self, target: str) -> None:
        out = _run("SELECT NVL2(1, 'a', 'b') AS c FROM dual", "oracle", target)
        assert "NVL2" not in out and "CASE WHEN" in out

    @pytest.mark.parametrize("target", ["mysql", "postgresql", "tsql"])
    def test_decode_to_case(self, target: str) -> None:
        out = _run(
            "SELECT DECODE(1, 1, 'one', 2, 'two', 'x') AS d FROM dual", "oracle", target
        )
        assert "DECODE" not in out and out.count("WHEN") == 2 and "ELSE" in out


class TestDateTimeFunctions:
    def test_now_and_curdate(self) -> None:
        for target in ("oracle", "tsql", "postgresql"):
            assert "NOW(" not in _run("SELECT NOW() AS n", "mysql", target)
            assert "CURDATE" not in _run("SELECT CURDATE() AS d", "mysql", target)

    def test_current_date_no_parens(self) -> None:
        for target in ("oracle", "tsql"):
            out = _run("SELECT CURRENT_DATE AS d", "postgresql", target)
            assert "CURRENT_DATE()" not in out

    def test_datediff_two_arg(self) -> None:
        sql = (
            "SELECT DATEDIFF(CAST('2024-01-08' AS DATE), "
            "CAST('2024-01-01' AS DATE)) AS d"
        )
        for target in ("oracle", "postgresql", "tsql"):
            _run(sql, "mysql", target)

    def test_to_char_format_model(self) -> None:
        sql = "SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD') AS d FROM dual"
        assert "DATE_FORMAT" in _run(sql, "oracle", "mysql")
        assert "'%Y-%M-%D'" in _run(sql, "oracle", "mysql")  # strftime tokens
        assert "FORMAT" in _run(sql, "oracle", "tsql")

    def test_to_date_format_model(self) -> None:
        sql = "SELECT TO_DATE('2024-01-01', 'YYYY-MM-DD') AS d FROM dual"
        assert "TO_DATE" in _run(sql, "oracle", "postgresql")
        _run(sql, "oracle", "tsql")


class TestNumericAndCast:
    def test_trunc_number(self) -> None:
        assert "TRUNCATE" in _run("SELECT TRUNC(3.7) AS t FROM dual", "oracle", "mysql")
        assert "ROUND" in _run("SELECT TRUNC(3.7) AS t FROM dual", "oracle", "tsql")

    def test_cast_int_to_mysql_signed(self) -> None:
        assert "SIGNED" in _run("SELECT CAST('1' AS INT) AS i", "tsql", "mysql")

    def test_cast_boolean(self) -> None:
        assert "SIGNED" in _run("SELECT CAST(1 AS BOOLEAN) AS b", "postgresql", "mysql")
        assert "BIT" in _run("SELECT CAST(1 AS BOOLEAN) AS b", "postgresql", "tsql")

    def test_convert_to_cast(self) -> None:
        out = _run("SELECT CONVERT(VARCHAR(20), 12345) AS s", "tsql", "postgresql")
        assert "CAST" in out and "CONVERT" not in out
        assert "CHAR" in _run("SELECT CONVERT(VARCHAR(20), 1) AS s", "tsql", "mysql")


class TestStringConcatChain:
    def test_plus_chain_all_concat(self) -> None:
        # Every "+" between string literals must become the concat operator.
        for target in ("oracle", "postgresql"):
            out = _run("SELECT 'a' + 'b' + 'c' AS s", "tsql", target)
            assert "+" not in out  # no leftover arithmetic + on string literals
