# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Tests for the engine runner's statement splitter and an end-to-end smoke
test of the harness mechanics using SQLite (no external engine required).

The splitter is the delicate, engine-specific part of the runner; it is verified
in isolation here. The SQLite smoke test proves the read+compare pipeline reaches
``expected_state.yaml`` from a real (if stand-in) database, so when you wire up
the four real engines in your DB-enabled environment, only the connection and
the transpiler's per-engine output remain to validate.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tests.functional_equivalence.engine_runner import split_statements
from tests.functional_equivalence.state_check import check_state, load_expected_state

_HERE = Path(__file__).parent


class TestSplitStatements:
    def test_tsql_splits_on_go(self) -> None:
        sql = "INSERT INTO t VALUES (1);\nGO\nINSERT INTO t VALUES (2);\nGO"
        stmts = split_statements(sql, "tsql")
        assert len(stmts) == 2
        assert "VALUES (1)" in stmts[0]
        assert "VALUES (2)" in stmts[1]

    def test_postgresql_splits_on_semicolons(self) -> None:
        sql = "INSERT INTO t VALUES (1);\nINSERT INTO t VALUES (2);"
        stmts = split_statements(sql, "postgresql")
        assert len(stmts) == 2

    def test_postgresql_keeps_dollar_quoted_body_intact(self) -> None:
        sql = (
            "CREATE FUNCTION f() RETURNS TRIGGER AS $$\n"
            "BEGIN\n  UPDATE t SET a = 1; RETURN NULL;\nEND;\n$$;\n"
            "INSERT INTO t VALUES (1);"
        )
        stmts = split_statements(sql, "postgresql")
        # The function body (with inner ';') stays one statement.
        assert len(stmts) == 2
        assert "$$" in stmts[0]
        assert "RETURN NULL" in stmts[0]

    def test_mysql_keeps_begin_end_body_intact(self) -> None:
        sql = (
            "CREATE TRIGGER trg AFTER INSERT ON t FOR EACH ROW\n"
            "BEGIN\n  UPDATE u SET a = 1; END;\n"
            "INSERT INTO t VALUES (1);"
        )
        stmts = split_statements(sql, "mysql")
        assert len(stmts) == 2
        assert "BEGIN" in stmts[0] and "END" in stmts[0]

    def test_oracle_splits_on_slash(self) -> None:
        sql = "BEGIN\n  proc();\nEND;\n/\n" "INSERT INTO t VALUES (1);\n"
        stmts = split_statements(sql, "oracle")
        assert any("BEGIN" in s and "proc()" in s for s in stmts)
        assert any("INSERT" in s for s in stmts)

    def test_line_comment_with_apostrophe_does_not_swallow_semicolons(
        self,
    ) -> None:
        # A '--' comment with an apostrophe (or the words BEGIN/END) must not be
        # treated as opening a string / block, which would merge every following
        # statement into one.
        sql = (
            "-- pay invoice 2's total now\n"
            "INSERT INTO t VALUES (1);\n"
            "-- BEGIN here is just prose, not a block\n"
            "INSERT INTO t VALUES (2);\n"
        )
        for dialect in ("postgresql", "mysql"):
            stmts = split_statements(sql, dialect)
            assert len(stmts) == 2, f"{dialect}: {stmts}"

    def test_block_comment_is_ignored(self) -> None:
        sql = (
            "/* note: don't split here; END */\n"
            "INSERT INTO t VALUES (1);\n"
            "INSERT INTO t VALUES (2);\n"
        )
        stmts = split_statements(sql, "postgresql")
        assert len(stmts) == 2

    def test_mysql_delimiter_directive_splits_routines(self) -> None:
        # MySQL uses DELIMITER // around routine bodies (whose inner ';' must not
        # split). The splitter must honor the active delimiter and drop the
        # DELIMITER directives themselves.
        sql = (
            "INSERT INTO t VALUES (1);\n"
            "DELIMITER //\n"
            "CREATE TRIGGER trg BEFORE INSERT ON t FOR EACH ROW\n"
            "BEGIN\n  SET NEW.x = 1;\nEND //\n"
            "CREATE PROCEDURE p()\n"
            "BEGIN\n  INSERT INTO u VALUES (1);\n  INSERT INTO u VALUES (2);\nEND //\n"
            "DELIMITER ;\n"
            "INSERT INTO t VALUES (2);\n"
        )
        stmts = split_statements(sql, "mysql")
        # 2 plain INSERTs + the trigger + the procedure = 4; no DELIMITER lines,
        # and no stray '//' clinging to a routine.
        assert len(stmts) == 4, stmts
        assert not any(s.strip().upper().startswith("DELIMITER") for s in stmts)
        assert not any(s.rstrip().endswith("//") for s in stmts)
        proc = [s for s in stmts if "CREATE PROCEDURE" in s][0]
        assert proc.count("INSERT INTO u") == 2


class TestHarnessEndToEndSQLite:
    """Prove the read+compare pipeline reaches the expected state from a real
    database. SQLite stands in for a target engine; this exercises everything
    except the per-engine transpiled SQL and driver connection."""

    def test_expected_state_reached(self) -> None:
        con = sqlite3.connect(":memory:")
        con.executescript("""
            CREATE TABLE customer(id INTEGER PRIMARY KEY, name TEXT,
                email TEXT, notes TEXT);
            INSERT INTO customer VALUES
                (1,'Acme','billing@acme.test','no payment'),
                (2,'Globex','ap@globex.test','paid');
            CREATE TABLE product(id INTEGER PRIMARY KEY, name TEXT,
                unit_price NUMERIC);
            INSERT INTO product VALUES (1,'Widget',10.00),(2,'Gadget',25.50);
            CREATE TABLE invoice(id INTEGER PRIMARY KEY, customer_id INT,
                issued_on TEXT, total NUMERIC, is_paid INT);
            INSERT INTO invoice VALUES
                (1,1,'2024-01-15',61.05,0),(2,2,'2024-02-01',39.05,1);
            CREATE TABLE invoice_line(id INTEGER PRIMARY KEY, invoice_id INT,
                product_id INT, qty INT, unit_price NUMERIC, line_total NUMERIC);
            INSERT INTO invoice_line VALUES
                (1,1,1,3,10.00,30.00),(2,1,2,1,25.50,25.50),
                (3,2,1,1,10.00,10.00),(4,2,2,1,25.50,25.50);
            CREATE TABLE payment(id INTEGER PRIMARY KEY, invoice_id INT,
                paid_on TEXT, amount NUMERIC);
            INSERT INTO payment VALUES (1,2,'2024-02-05',39.05);
            CREATE TABLE app_flag(id INTEGER PRIMARY KEY, flag_name TEXT,
                enabled INT, note TEXT);
            INSERT INTO app_flag VALUES (1,'audit_log',1,'on'),(2,'beta_ui',0,NULL);
            """)

        def read_table(name: str) -> list[dict]:
            cur = con.execute(f"SELECT * FROM {name} ORDER BY id")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

        state = load_expected_state(_HERE / "expected_state.yaml")
        mismatches = check_state(state, read_table)
        assert mismatches == [], "\n".join(str(m) for m in mismatches)
        con.close()
