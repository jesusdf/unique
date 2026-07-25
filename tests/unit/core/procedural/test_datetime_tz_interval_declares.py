# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Multi-word datetime/interval types in a PL/SQL declaration section.

``v TIMESTAMP WITH LOCAL TIME ZONE`` (and the plain ``WITH TIME ZONE`` /
``WITHOUT TIME ZONE`` / ``INTERVAL YEAR TO MONTH`` / ``INTERVAL DAY TO SECOND``
family) must parse as ONE compound type, not splinter into garbage statements.
The transformer then maps the compound per target, reusing the DDL
``emit_ddl._local_tz_gap`` decisions (PG timestamptz faithful; tsql/mysql
annotated + warned; Oracle keeps its native spelling).
"""

from __future__ import annotations

from unique.core.ast_nodes import DeclareStatement
from unique.core.procedural.parser import ProceduralParser
from unique.core.transpiler import Transpiler

t = Transpiler()


def _declares(sql: str, dialect: str):
    node = ProceduralParser(dialect).parse(sql).node
    return [s for s in node.body if isinstance(s, DeclareStatement)]


def _proc(decl: str) -> str:
    return f"CREATE OR REPLACE PROCEDURE p IS {decl} BEGIN NULL; END;"


class TestCompoundTokenization:
    def test_with_local_time_zone_is_one_type(self) -> None:
        d = _declares(_proc("v TIMESTAMP WITH LOCAL TIME ZONE;"), "oracle")
        assert len(d) == 1, d
        assert d[0].data_type.name.upper() == "TIMESTAMP WITH LOCAL TIME ZONE"

    def test_with_time_zone_is_one_type(self) -> None:
        d = _declares(_proc("v TIMESTAMP WITH TIME ZONE;"), "oracle")
        assert len(d) == 1, d
        assert d[0].data_type.name.upper() == "TIMESTAMP WITH TIME ZONE"

    def test_without_time_zone_is_one_type(self) -> None:
        d = _declares(_proc("v TIMESTAMP WITHOUT TIME ZONE;"), "oracle")
        assert len(d) == 1, d
        assert d[0].data_type.name.upper() == "TIMESTAMP WITHOUT TIME ZONE"

    def test_precision_before_with_time_zone(self) -> None:
        d = _declares(_proc("v TIMESTAMP(6) WITH TIME ZONE;"), "oracle")
        assert len(d) == 1, d
        assert d[0].data_type.name.upper() == "TIMESTAMP WITH TIME ZONE"
        assert d[0].data_type.params == (6,)

    def test_interval_year_to_month_is_one_type(self) -> None:
        d = _declares(_proc("v INTERVAL YEAR TO MONTH;"), "oracle")
        assert len(d) == 1, d
        assert d[0].data_type.name.upper() == "INTERVAL YEAR TO MONTH"

    def test_interval_day_to_second_is_one_type(self) -> None:
        d = _declares(_proc("v INTERVAL DAY TO SECOND;"), "oracle")
        assert len(d) == 1, d
        assert d[0].data_type.name.upper() == "INTERVAL DAY TO SECOND"

    def test_interval_precision_folded(self) -> None:
        d = _declares(_proc("v INTERVAL DAY(2) TO SECOND(6);"), "oracle")
        assert len(d) == 1, d
        assert d[0].data_type.name.upper() == "INTERVAL DAY(2) TO SECOND(6)"

    def test_no_splinter_statements(self) -> None:
        # The whole routine parses cleanly: exactly one declare, no leftover
        # RawSQL/PassthroughSQL splinters ("WITH LOCAL;", "TIME ZONE;").
        node = (
            ProceduralParser("oracle")
            .parse(_proc("v TIMESTAMP WITH LOCAL TIME ZONE;"))
            .node
        )
        declares = [s for s in node.body if isinstance(s, DeclareStatement)]
        assert len(declares) == 1
        assert all(type(s).__name__ != "RawSQL" for s in node.body), node.body


class TestPerTargetMapping:
    def _out(self, decl: str, target: str):
        return t.transpile(_proc(decl), "oracle", target)

    def test_local_tz_postgres_maps_timestamptz_warned(self) -> None:
        r = self._out("v TIMESTAMP WITH LOCAL TIME ZONE;", "postgresql")
        up = r.sql.upper()
        assert "TIMESTAMPTZ" in up, r.sql
        # original spelling survives only inside the carrier, never as garbage
        assert "WITH LOCAL;" not in up and "TIME ZONE;" not in up, r.sql
        assert r.warnings, r.sql

    def test_local_tz_tsql_maps_datetimeoffset_warned(self) -> None:
        r = self._out("v TIMESTAMP WITH LOCAL TIME ZONE;", "tsql")
        assert "DATETIMEOFFSET" in r.sql.upper(), r.sql
        assert r.warnings, r.sql

    def test_local_tz_mysql_maps_timestamp_warned(self) -> None:
        r = self._out("v TIMESTAMP WITH LOCAL TIME ZONE;", "mysql")
        up = r.sql.upper()
        assert "TIMESTAMP" in up, r.sql
        assert "WITH LOCAL;" not in up, r.sql
        assert r.warnings, r.sql

    def test_local_tz_oracle_keeps_native(self) -> None:
        r = self._out("v TIMESTAMP WITH LOCAL TIME ZONE;", "oracle")
        assert "TIMESTAMP WITH LOCAL TIME ZONE" in r.sql.upper(), r.sql

    def test_with_time_zone_postgres_faithful(self) -> None:
        # Plain WITH TIME ZONE == PG timestamptz exactly: faithful, no garbage.
        r = self._out("v TIMESTAMP WITH TIME ZONE;", "postgresql")
        up = r.sql.upper()
        assert "TIMESTAMPTZ" in up, r.sql
        assert "TIME ZONE;" not in up, r.sql

    def test_without_time_zone_reduces_to_base(self) -> None:
        r = self._out("v TIMESTAMP WITHOUT TIME ZONE;", "postgresql")
        up = r.sql.upper()
        assert "TIMESTAMP" in up, r.sql
        assert "WITHOUT" not in up, r.sql

    def test_interval_ytm_postgres_faithful(self) -> None:
        r = self._out("v INTERVAL YEAR TO MONTH;", "postgresql")
        assert "INTERVAL YEAR TO MONTH" in r.sql.upper(), r.sql

    def test_interval_dts_tsql_degrades_text_warned(self) -> None:
        r = self._out("v INTERVAL DAY TO SECOND;", "tsql")
        assert "VARCHAR" in r.sql.upper(), r.sql
        assert r.warnings, r.sql

    def test_precision_position_oracle_native(self) -> None:
        # Oracle wants the precision on the base field, not after the
        # qualifier: TIMESTAMP(6) WITH TIME ZONE, never ...ZONE(6).
        r = self._out("v TIMESTAMP(6) WITH TIME ZONE;", "oracle")
        up = r.sql.upper()
        assert "TIMESTAMP(6) WITH TIME ZONE" in up, r.sql
        assert "ZONE(6)" not in up, r.sql

    def test_precision_position_postgres(self) -> None:
        r = self._out("v TIMESTAMP(6) WITH TIME ZONE;", "postgresql")
        assert "TIMESTAMPTZ(6)" in r.sql.upper(), r.sql

    def test_interval_precision_postgres_valid_warned(self) -> None:
        # PG cannot express a leading-field precision; strip to the bare
        # qualifier and carry the original (warned).
        r = self._out("v INTERVAL DAY(2) TO SECOND(6);", "postgresql")
        up = r.sql.upper()
        assert "INTERVAL DAY TO SECOND" in up, r.sql
        assert "DAY(2)" not in up.split("UNIQUE:")[0], r.sql
        assert r.warnings, r.sql


class TestRoundTrip:
    def test_oracle_pg_oracle_restores_original_spellings(self) -> None:
        # The /* UNIQUE */ carrier lets a reverse pass restore the exact
        # Oracle spelling (LOCAL TIME ZONE + per-field interval precision).
        decl = (
            "v TIMESTAMP WITH LOCAL TIME ZONE; "
            "x TIMESTAMP(6) WITH TIME ZONE; "
            "z INTERVAL DAY(2) TO SECOND(6);"
        )
        ora = f"CREATE OR REPLACE PROCEDURE p IS {decl} BEGIN NULL; END;"
        pg = t.transpile(ora, "oracle", "postgresql").sql
        back = t.transpile(pg, "postgresql", "oracle").sql.upper()
        assert "TIMESTAMP WITH LOCAL TIME ZONE" in back, back
        assert "TIMESTAMP(6) WITH TIME ZONE" in back, back
        assert "INTERVAL DAY(2) TO SECOND(6)" in back, back
