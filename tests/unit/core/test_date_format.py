"""Date-part extraction and date-format-model translation.

`DATEPART`/`EXTRACT` must emit the `EXTRACT(part FROM x)` form (the comma form is
rejected by every engine), and the format-model translation must respect the
four conventions — Oracle, MySQL DATE_FORMAT, T-SQL .NET, and Python-strftime
(sqlglot's canonical). The `mm`/`MM` (minute vs month) case-sensitivity bug is
pinned here. Round-trips were validated live against real engines.
"""

import sqlglot

from unique.core.converter.emit import _convert_date_format as cf
from unique.core.transpiler import Transpiler

_READ = {"tsql": "tsql", "postgresql": "postgres", "mysql": "mysql", "oracle": "oracle"}

t = Transpiler()


def _valid(sql: str, dialect: str) -> None:
    sqlglot.parse(sql, read=_READ[dialect], error_level=sqlglot.ErrorLevel.RAISE)


class TestDatePart:
    def test_extract_uses_from_not_comma(self) -> None:
        for target in ("oracle", "postgresql", "mysql"):
            out = t.transpile("SELECT DATEPART(year, d) AS r", "tsql", target).sql
            assert "EXTRACT(YEAR FROM" in out.upper(), (target, out)
            assert "EXTRACT(YEAR," not in out.upper().replace(" ", "")
            _valid(out, target)


class TestDateFormatModel:
    def test_dotnet_case_sensitive_minute_vs_month(self) -> None:
        # 'MM' is month, 'mm' is minute in .NET — the whole reason for the bug.
        assert cf("yyyy-MM-dd HH:mm:ss", "tsql", "mysql") == "%Y-%m-%d %H:%i:%s"
        assert cf("yyyy-MM-dd HH:mm:ss", "tsql", "oracle") == "YYYY-MM-DD HH24:MI:SS"

    def test_python_strftime_is_sqlglot_canonical(self) -> None:
        # sqlglot normalizes FORMAT/DATE_FORMAT to Python strftime (%M = minute).
        assert cf("%Y-%m-%d %H:%M:%S", "python", "mysql") == "%Y-%m-%d %H:%i:%s"
        assert cf("%Y-%m-%d %H:%M:%S", "python", "oracle") == "YYYY-MM-DD HH24:MI:SS"
        assert cf("%Y-%m-%d %H:%M:%S", "python", "tsql") == "yyyy-MM-dd HH:mm:ss"

    def test_ampm_and_names(self) -> None:
        assert cf("hh:mm tt", "tsql", "mysql") == "%h:%i %p"
        assert cf("MMMM", "tsql", "oracle") == "MONTH"


class TestFormatFunctionLive:
    def test_tsql_format_to_mysql_no_month_for_minute(self) -> None:
        # Regression: FORMAT(d, 'yyyy-MM-dd HH:mm:ss') -> mysql used to render the
        # minute as the month name ('14:June:05').
        out = t.transpile(
            "SELECT FORMAT(d, 'yyyy-MM-dd HH:mm:ss') AS r", "tsql", "mysql"
        ).sql
        assert "%i:%s" in out and "%M" not in out, out
        _valid(out, "mysql")

    def test_to_char_across_targets(self) -> None:
        for target, needle in (
            ("mysql", "DATE_FORMAT"),
            ("postgresql", "TO_CHAR"),
            ("tsql", "FORMAT"),
        ):
            out = t.transpile(
                "SELECT TO_CHAR(d, 'YYYY-MM-DD') AS r", "oracle", target
            ).sql
            assert needle in out, (target, out)
            _valid(out, target)


class TestDatetimeCast:
    """T-SQL DATETIME/DATETIME2/SMALLDATETIME are not Oracle/PostgreSQL types;
    CAST must map them to TIMESTAMP (validated live for non-literal values)."""

    def test_datetime_maps_to_timestamp(self) -> None:
        for typ in ("DATETIME", "DATETIME2", "SMALLDATETIME"):
            for target in ("oracle", "postgresql"):
                out = t.transpile(f"SELECT CAST(c AS {typ}) AS r", "tsql", target).sql
                assert "AS TIMESTAMP)" in out.upper(), (typ, target, out)
                _valid(out, target)

    def test_datetime_stays_native_on_mysql(self) -> None:
        out = t.transpile("SELECT CAST(c AS DATETIME2) AS r", "tsql", "mysql").sql
        assert "AS DATETIME)" in out.upper(), out
        _valid(out, "mysql")
