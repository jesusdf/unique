# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Standalone ``JSON_QUERY(x, path)`` routes to each target's object accessor.

RED seed (B13 follow-up, 2026-07-25): T-SQL ``JSON_QUERY`` parses as
``exp.JSONExtract`` and was modelled as a ``JSON_EXTRACT`` call whose emission
only knew the mysql-source spelling, so a T-SQL-source query shipped an
*executable* ``JSON_EXTRACT(...)`` on Oracle and PostgreSQL — engines that have
no such function (runtime error, zero warnings). Oracle and T-SQL have
``JSON_QUERY`` natively; PostgreSQL routes through the SQL/JSON path engine.
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


class TestJsonQueryAccessor:
    SRC = "SELECT JSON_QUERY(doc, '$.items') AS items FROM docs;"

    def test_tsql_json_query_to_oracle_uses_native_json_query(self) -> None:
        out = Transpiler().transpile(self.SRC, "tsql", "oracle").sql
        assert "JSON_QUERY(doc, '$.items')" in out, out
        # Oracle has no JSON_EXTRACT — the leak must be gone.
        assert "JSON_EXTRACT" not in out.upper(), out
        _parse_ok(out, "oracle")

    def test_tsql_json_query_to_postgresql_routes_path_engine(self) -> None:
        out = Transpiler().transpile(self.SRC, "tsql", "postgresql").sql
        assert "JSONB_PATH_QUERY_FIRST" in out, out
        assert "JSON_EXTRACT" not in out.upper(), out
        _parse_ok(out, "postgresql")

    def test_tsql_json_query_to_mysql_uses_native_json_extract(self) -> None:
        out = Transpiler().transpile(self.SRC, "tsql", "mysql").sql
        # MySQL's object accessor IS JSON_EXTRACT — valid there.
        assert "JSON_EXTRACT(doc, '$.items')" in out, out
        _parse_ok(out, "mysql")

    def test_oracle_json_query_to_tsql_uses_native_json_query(self) -> None:
        out = Transpiler().transpile(self.SRC, "oracle", "tsql").sql
        assert "JSON_QUERY(doc, '$.items')" in out, out
        assert "JSON_EXTRACT" not in out.upper(), out
        _parse_ok(out, "tsql")
