"""Date arithmetic translation (audit 2026-07-02, S1-4).

v0.7.0 emitted ``DATE_ADD(ts, 7, DAY)`` — invalid on every engine — and let
sqlglot's internal ``TIME_STR_TO_TIME`` pseudo-function leak into DATEDIFF
output. Each target needs its own idiom.
"""

import sqlglot

from unique.core.transpiler import Transpiler

_READ = {"tsql": "tsql", "postgresql": "postgres", "mysql": "mysql", "oracle": "oracle"}


def _valid(sql: str, dialect: str) -> None:
    sqlglot.parse(sql, read=_READ[dialect], error_level=sqlglot.ErrorLevel.RAISE)


class TestDateAdd:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_tsql_dateadd_to_mysql_uses_interval(self) -> None:
        out = self.t.transpile("SELECT DATEADD(day, 7, d) FROM t", "tsql", "mysql").sql
        assert "DATE_ADD(d, INTERVAL 7 DAY)" in out
        _valid(out, "mysql")

    def test_tsql_dateadd_to_postgresql(self) -> None:
        out = self.t.transpile(
            "SELECT DATEADD(month, 3, d) FROM t", "tsql", "postgresql"
        ).sql
        assert "d + INTERVAL '3 MONTH'" in out
        _valid(out, "postgresql")

    def test_tsql_dateadd_to_oracle_months(self) -> None:
        out = self.t.transpile(
            "SELECT DATEADD(month, 3, d) FROM t", "tsql", "oracle"
        ).sql
        assert "ADD_MONTHS(d, 3)" in out
        _valid(out, "oracle")

    def test_tsql_dateadd_to_oracle_days(self) -> None:
        out = self.t.transpile("SELECT DATEADD(day, 7, d) FROM t", "tsql", "oracle").sql
        assert "NUMTODSINTERVAL(7, 'DAY')" in out
        _valid(out, "oracle")

    def test_mysql_date_sub_to_tsql(self) -> None:
        out = self.t.transpile(
            "SELECT DATE_SUB(d, INTERVAL 1 MONTH) FROM t", "mysql", "tsql"
        ).sql
        assert "DATEADD(MONTH, -1, d)" in out
        _valid(out, "tsql")

    def test_mysql_date_add_roundtrip_identity(self) -> None:
        out = self.t.transpile(
            "SELECT DATE_ADD(d, INTERVAL 7 DAY) FROM t", "mysql", "mysql"
        ).sql
        assert "DATE_ADD(d, INTERVAL 7 DAY)" in out
        _valid(out, "mysql")


class TestDateDiff:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_tsql_datediff_to_mysql_day(self) -> None:
        out = self.t.transpile("SELECT DATEDIFF(day, a, b) FROM t", "tsql", "mysql").sql
        assert "DATEDIFF(b, a)" in out
        assert "TIME_STR_TO_TIME" not in out
        _valid(out, "mysql")

    def test_tsql_datediff_to_postgresql_day(self) -> None:
        out = self.t.transpile(
            "SELECT DATEDIFF(day, a, b) FROM t", "tsql", "postgresql"
        ).sql
        assert "CAST(b AS DATE) - CAST(a AS DATE)" in out
        assert "TIME_STR_TO_TIME" not in out
        _valid(out, "postgresql")

    def test_tsql_datediff_to_oracle_day(self) -> None:
        out = self.t.transpile(
            "SELECT DATEDIFF(day, a, b) FROM t", "tsql", "oracle"
        ).sql
        assert "TRUNC(CAST(b AS DATE)) - TRUNC(CAST(a AS DATE))" in out
        _valid(out, "oracle")

    def test_tsql_datediff_month_boundary_semantics(self) -> None:
        out = self.t.transpile(
            "SELECT DATEDIFF(month, a, b) FROM t", "tsql", "mysql"
        ).sql
        # Boundary count, not elapsed months.
        assert "YEAR(b) * 12 + MONTH(b)" in out
        _valid(out, "mysql")

    def test_datediff_to_tsql_keeps_native_form(self) -> None:
        out = self.t.transpile("SELECT DATEDIFF(day, a, b) FROM t", "tsql", "tsql").sql
        assert "DATEDIFF(DAY, a, b)" in out or "DATEDIFF(day, a, b)" in out
        _valid(out, "tsql")
