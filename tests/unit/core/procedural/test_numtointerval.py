# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Oracle ``NUMTODSINTERVAL(n, 'unit')`` / ``NUMTOYMINTERVAL(n, 'unit')`` build a
standalone INTERVAL value that PostgreSQL has no constructor for; the exact
equivalent is ``n * INTERVAL '1 <unit>'`` (or ``INTERVAL '<n> <unit>'`` for a
literal count). Before the B36 fix the call leaked untranslated into the emitted
body and the output gate degraded the whole routine (UNIQUE-1151).

The call appears in three contexts that flow through different pipelines, so all
three are covered: a RETURN expression, an assignment RHS, and embedded DML.
"""

from __future__ import annotations

from unique.core.transpiler import Transpiler

t = Transpiler()


def _pg(oracle: str) -> object:
    return t.transpile(oracle, "oracle", "postgresql")


class TestNumToIntervalToPostgres:
    def test_return_expression_literal_count(self) -> None:
        res = _pg(
            "CREATE OR REPLACE FUNCTION f RETURN DATE AS\nBEGIN\n"
            "    RETURN SYSDATE + NUMTODSINTERVAL(-3, 'DAY');\nEND;"
        )
        up = res.sql.upper()
        assert "NUMTODSINTERVAL" not in up, res.sql
        assert "INTERVAL '-3 DAY'" in up, res.sql
        assert not any(w.code == "UNIQUE-1151" for w in res.warnings), res.sql

    def test_assignment_rhs_variable_count(self) -> None:
        res = _pg(
            "CREATE OR REPLACE PROCEDURE p AS\n    v_base DATE;\n    v_n NUMBER;"
            "\n    v_out DATE;\nBEGIN\n"
            "    v_out := v_base + NUMTODSINTERVAL(v_n, 'MINUTE');\nEND;"
        )
        up = res.sql.upper()
        assert "NUMTODSINTERVAL" not in up, res.sql
        assert "INTERVAL '1 MINUTE'" in up, res.sql
        assert not any(w.code == "UNIQUE-1151" for w in res.warnings), res.sql

    def test_embedded_dml_where_clause(self) -> None:
        res = _pg(
            "CREATE OR REPLACE PROCEDURE p AS\nBEGIN\n"
            "    UPDATE tbl_6 SET col_32 = 0\n"
            "    WHERE col_32 = 1 AND SYSDATE > col_33 + NUMTODSINTERVAL(5, 'MINUTE');"
            "\nEND;"
        )
        up = res.sql.upper()
        assert "NUMTODSINTERVAL" not in up, res.sql
        assert "INTERVAL '5 MINUTE'" in up, res.sql
        assert not any(w.code == "UNIQUE-1151" for w in res.warnings), res.sql

    def test_year_month_interval(self) -> None:
        res = _pg(
            "CREATE OR REPLACE FUNCTION f RETURN DATE AS\nBEGIN\n"
            "    RETURN SYSDATE + NUMTOYMINTERVAL(2, 'MONTH');\nEND;"
        )
        up = res.sql.upper()
        assert "NUMTOYMINTERVAL" not in up, res.sql
        assert "INTERVAL '2 MONTH'" in up, res.sql
        assert not any(w.code == "UNIQUE-1151" for w in res.warnings), res.sql
