# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Trigger transpilation across engines.

Covers the firing-mode surface that differs between dialects:

- timing: BEFORE / AFTER / INSTEAD OF
- granularity: row-level (FOR EACH ROW) vs statement-level

and the structural differences in how each engine declares a trigger
(PostgreSQL needs a separate trigger function; MySQL has no INSTEAD OF).

Engine hazards such as Oracle's mutating-table error (a row-level trigger that
queries or modifies its own table) are documented here as known limitations;
a faithful automatic rewrite is not generally possible, so the transpiler
should preserve the body rather than silently "fix" it.
"""

from __future__ import annotations

import re

from unique.core.transpiler import Transpiler


def _t(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


class TestTriggerTiming:
    AFTER_INSERT = (
        "CREATE TRIGGER trg ON dbo.t\n"
        "AFTER INSERT\n"
        "AS\nBEGIN\n    UPDATE dbo.t SET n = 1 WHERE id = 1\nEND"
    )

    def test_after_insert_oracle(self) -> None:
        out = _t(self.AFTER_INSERT, "tsql", "oracle")
        assert "AFTER INSERT ON t" in out
        assert "dbo." not in out

    def test_after_insert_mysql(self) -> None:
        out = _t(self.AFTER_INSERT, "tsql", "mysql")
        assert "AFTER INSERT ON t" in out
        assert "FOR EACH ROW" in out

    def test_after_insert_postgresql_emits_function_and_trigger(self) -> None:
        out = _t(self.AFTER_INSERT, "tsql", "postgresql")
        # PostgreSQL needs a trigger function the trigger calls.
        assert "CREATE OR REPLACE FUNCTION trg_func()" in out
        assert "RETURNS TRIGGER" in out
        assert "EXECUTE FUNCTION trg_func();" in out
        # The body must be carried into the function, not dropped.
        assert "UPDATE t SET n = 1" in out
        # The old templating bug must not reappear.
        assert "{name}" not in out


class TestInsteadOfTrigger:
    INSTEAD_OF = (
        "CREATE TRIGGER trg ON dbo.v\n"
        "INSTEAD OF UPDATE\n"
        "AS\nBEGIN\n    SELECT 1\nEND"
    )

    def test_instead_of_documented_on_mysql(self) -> None:
        out = _t(self.INSTEAD_OF, "tsql", "mysql")
        # MySQL has no INSTEAD OF; it must be documented in a comment, not
        # emitted as an executable INSTEAD OF clause.
        code_lines = [ln for ln in out.splitlines() if not ln.strip().startswith("--")]
        assert all("INSTEAD OF" not in ln for ln in code_lines)
        assert "-- UNIQUE: MySQL has no INSTEAD OF trigger" in out
        assert "BEFORE UPDATE ON v" in out

    def test_instead_of_kept_on_postgresql(self) -> None:
        # PostgreSQL supports INSTEAD OF (on views); it should be preserved.
        out = _t(self.INSTEAD_OF, "tsql", "postgresql")
        assert "INSTEAD OF UPDATE ON v" in out


class TestTriggerGranularity:
    def test_row_level_kept_oracle(self) -> None:
        src = (
            "CREATE TRIGGER trg\n"
            "BEFORE INSERT ON t\n"
            "FOR EACH ROW\n"
            "BEGIN\n    NULL;\nEND;"
        )
        out = _t(src, "oracle", "postgresql")
        assert "FOR EACH ROW" in out


class TestMutatingTableHazard:
    """Oracle raises ORA-04091 when a row-level trigger queries/modifies its
    own table. We can't auto-rewrite that faithfully, so the body must be
    preserved (so a human can apply a compound-trigger / statement-level fix),
    not silently altered."""

    def test_self_referencing_body_preserved(self) -> None:
        src = (
            "CREATE TRIGGER trg ON dbo.t\n"
            "AFTER INSERT\n"
            "AS\nBEGIN\n"
            "    UPDATE dbo.t SET n = (SELECT COUNT(*) FROM dbo.t)\nEND"
        )
        out = _t(src, "tsql", "oracle")
        # The self-referencing UPDATE/SELECT on the same table is preserved.
        assert "UPDATE t SET" in out
        assert "SELECT COUNT(*) FROM t" in out.replace("  ", " ")


def _tr(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


class TestTriggerUpdatePredicate:
    """T-SQL UPDATE(col) inside a trigger tests whether a column changed; it
    must be rewritten per engine, not emitted verbatim (invalid elsewhere)."""

    SRC = (
        "CREATE TRIGGER dbo.trg ON dbo.t\n"
        "FOR UPDATE\nAS\nBEGIN\n"
        "    IF UPDATE(col_32)\n"
        "    BEGIN\n        INSERT INTO dbo.log (a) VALUES (1)\n    END\n"
        "END"
    )

    def test_mysql(self) -> None:
        out = _tr(self.SRC, "tsql", "mysql")
        assert "NOT (NEW.col_32 <=> OLD.col_32)" in out
        assert "UPDATE(col_32)" not in out.replace(" ", "")

    def test_postgresql(self) -> None:
        out = _tr(self.SRC, "tsql", "postgresql")
        assert "NEW.col_32 IS DISTINCT FROM OLD.col_32" in out

    def test_oracle(self) -> None:
        out = _tr(self.SRC, "tsql", "oracle")
        assert "UPDATING('col_32')" in out

    def test_plain_update_statement_untouched(self) -> None:
        src = "CREATE PROCEDURE dbo.p AS BEGIN UPDATE t SET a = 1 END"
        out = _tr(src, "tsql", "mysql")
        assert "UPDATE t SET a = 1" in out
        assert "NEW." not in out


class TestTriggerPseudoTables:
    """T-SQL inserted/deleted pseudo-tables in a trigger body: column qualifiers
    map to the row-level NEW/OLD; a set-based use (FROM/JOIN) is documented
    (no row-level equivalent)."""

    def _t(self, sql: str, target: str) -> str:
        return Transpiler().transpile(sql, source="tsql", target=target).sql

    _COL_QUALIFIER = (
        "CREATE TRIGGER trg ON t AFTER UPDATE AS BEGIN "
        "UPDATE t SET audit = inserted.col1 WHERE id = inserted.id END"
    )
    _SET_BASED = (
        "CREATE TRIGGER trg ON t AFTER UPDATE AS BEGIN "
        "INSERT INTO audit (a) SELECT i.col1 FROM inserted i JOIN deleted d "
        "ON d.id = i.id END"
    )

    def test_qualifier_to_new_old_pg_mysql(self) -> None:
        for target in ("postgresql", "mysql"):
            out = self._t(self._COL_QUALIFIER, target)
            assert "NEW.col1" in out
            assert "NEW.id" in out
            # the qualifier must not be stripped to a bare/ambiguous column
            assert "= col1 WHERE" not in out

    def test_qualifier_to_new_old_oracle(self) -> None:
        out = self._t(self._COL_QUALIFIER, "oracle")
        assert ":NEW.col1" in out
        assert ":NEW.id" in out

    def test_deleted_maps_to_old(self) -> None:
        src = (
            "CREATE TRIGGER trg ON t AFTER UPDATE AS BEGIN "
            "UPDATE t SET a = deleted.col1 END"
        )
        assert "OLD.col1" in self._t(src, "postgresql")
        assert ":OLD.col1" in self._t(src, "oracle")

    def test_set_based_documented(self) -> None:
        # PostgreSQL now rewrites a pure set-based trigger with transition tables
        # (see TestSetBasedTriggerRewrite); Oracle and MySQL still document it.
        for target in ("mysql", "oracle"):
            out = self._t(self._SET_BASED, target)
            assert "set-based inserted/deleted" in out
            # the original statement is commented out, not emitted as runnable
            code = [ln for ln in out.splitlines() if not ln.strip().startswith("--")]
            assert all("FROM inserted" not in ln for ln in code)

    def test_qualifier_not_applied_outside_trigger(self) -> None:
        # An OUTPUT inserted.col in a plain procedure keeps its own handling
        # (RETURNING/strip), not the trigger NEW/OLD mapping.
        src = (
            "CREATE PROCEDURE p AS BEGIN "
            "INSERT INTO t (a) OUTPUT inserted.id INTO @v VALUES (1) END"
        )
        out = self._t(src, "postgresql")
        assert "NEW.id" not in out


class TestSetBasedTriggerRewrite:
    """A *purely* set-based trigger (uses only FROM/JOIN inserted/deleted, with
    no row-level qualifier or UPDATE(col) predicate) is rewritten to the target's
    set-based trigger form rather than merely documented — where the target has a
    faithful equivalent:

    - PostgreSQL: a statement-level trigger (FOR EACH STATEMENT) whose function
      declares REFERENCING NEW TABLE AS inserted OLD TABLE AS deleted. This is a
      direct, faithful mapping of T-SQL's named inserted/deleted tables.
    - Oracle: documented. Oracle has no named transition tables; a compound
      trigger would require accumulating rows into a PL/SQL collection, which is
      not a mechanical rewrite, so emitting it would risk invalid SQL.
    - MySQL: documented (no transition tables at all).

    A *mixed* trigger (row-level and set-level uses together) cannot be a single
    trigger and stays documented on every target.
    """

    def _t(self, sql: str, target: str) -> str:
        return Transpiler().transpile(sql, source="tsql", target=target).sql

    _PURE_SET_BASED = (
        "CREATE TRIGGER trg ON t AFTER UPDATE AS BEGIN "
        "INSERT INTO audit (a, b) "
        "SELECT i.col1, d.col1 FROM inserted i JOIN deleted d ON d.id = i.id "
        "END"
    )
    _MIXED = (
        "CREATE TRIGGER trg ON t AFTER UPDATE AS BEGIN "
        "IF UPDATE(col1) "
        "INSERT INTO audit (a) SELECT i.col1 FROM inserted i WHERE i.id = inserted.id "
        "END"
    )

    def test_pure_set_based_to_postgresql_uses_transition_tables(self) -> None:
        out = self._t(self._PURE_SET_BASED, "postgresql")
        assert "REFERENCING NEW TABLE AS inserted OLD TABLE AS deleted" in out
        assert "FOR EACH STATEMENT" in out
        code = "\n".join(
            ln for ln in out.splitlines() if not ln.strip().startswith("--")
        )
        assert "FROM inserted" in code
        assert "JOIN deleted" in code

    _SET_BASED_UPDATE = (
        "CREATE TRIGGER trg ON invoice_line AFTER INSERT, UPDATE AS BEGIN "
        "UPDATE il SET il.line_total = il.qty * il.unit_price "
        "FROM invoice_line il INNER JOIN inserted i ON i.id = il.id "
        "END"
    )

    def test_set_based_update_body_is_valid_postgresql(self) -> None:
        # A set-based trigger whose body is an UPDATE ... FROM ... JOIN inserted
        # must emit a PostgreSQL-valid UPDATE (target table once, source in FROM,
        # join predicate in WHERE), not the raw T-SQL "UPDATE alias SET
        # alias.col ... FROM tbl alias JOIN ..." that fails at runtime.
        out = self._t(self._SET_BASED_UPDATE, "postgresql")
        code = "\n".join(
            ln for ln in out.splitlines() if not ln.strip().startswith("--")
        )
        assert "FOR EACH STATEMENT" in out
        # The body must be preserved (not degraded to a comment) ...
        assert "UPDATE" in code
        assert "set-based inserted/deleted" not in out
        # ... and rendered in PostgreSQL's UPDATE..FROM..WHERE form: no
        # "SET il.line_total" qualified-target and no duplicated source table.
        assert "SET il.line_total" not in code
        assert "FROM inserted" in code
        assert "WHERE" in code

    def test_pure_set_based_to_oracle_documented(self) -> None:
        # Oracle has no equivalent to T-SQL's named transition tables: a compound
        # trigger would need to accumulate rows into a PL/SQL collection, which
        # is not a mechanical rewrite of a set-based INSERT...SELECT. Emitting
        # "FROM inserted" would be invalid Oracle, so document instead.
        out = self._t(self._PURE_SET_BASED, "oracle")
        assert "set-based inserted/deleted" in out
        code = [ln for ln in out.splitlines() if not ln.strip().startswith("--")]
        assert all("FROM inserted" not in ln for ln in code)

    def test_pure_set_based_to_mysql_documented(self) -> None:
        out = self._t(self._PURE_SET_BASED, "mysql")
        assert "set-based inserted/deleted" in out
        code = [ln for ln in out.splitlines() if not ln.strip().startswith("--")]
        assert all("FROM inserted" not in ln for ln in code)

    def test_mixed_trigger_stays_documented_everywhere(self) -> None:
        for target in ("postgresql", "oracle", "mysql"):
            out = self._t(self._MIXED, target)
            assert "set-based inserted/deleted" in out
            code = [ln for ln in out.splitlines() if not ln.strip().startswith("--")]
            assert all("FROM inserted" not in ln for ln in code)


class TestSetBasedTriggerEventRules:
    """PostgreSQL transition-table rules, surfaced by the first live FE run:

    - OLD TABLE may only be declared on DELETE/UPDATE triggers and NEW TABLE
      on INSERT/UPDATE ("ERROR: OLD TABLE can only be specified for a DELETE
      or UPDATE trigger").
    - A trigger with transition tables may have exactly ONE event ("ERROR:
      transition tables cannot be specified for triggers with more than one
      event"), so AFTER INSERT, UPDATE must split into one trigger per event.
    """

    def _t(self, sql: str) -> str:
        return Transpiler().transpile(sql, source="tsql", target="postgresql").sql

    def test_insert_only_trigger_declares_only_new_table(self) -> None:
        sql = (
            "CREATE TRIGGER trg_paid ON payment AFTER INSERT AS BEGIN "
            "UPDATE inv SET inv.is_paid = 1 FROM invoice AS inv "
            "WHERE inv.id IN (SELECT invoice_id FROM inserted) "
            "END"
        )
        out = self._t(sql)
        assert "REFERENCING NEW TABLE AS inserted" in out
        assert "OLD TABLE" not in out

    def test_multi_event_set_based_splits_into_one_trigger_per_event(self) -> None:
        sql = (
            "CREATE TRIGGER trg_total ON invoice_line AFTER INSERT, UPDATE AS BEGIN "
            "UPDATE inv SET inv.total = 1 FROM invoice AS inv "
            "WHERE inv.id IN (SELECT invoice_id FROM inserted "
            "UNION SELECT invoice_id FROM deleted) "
            "END"
        )
        out = self._t(sql)
        # No multi-event trigger with transition tables.
        assert "INSERT OR UPDATE" not in out and "INSERT, UPDATE" not in out
        assert out.count("CREATE OR REPLACE TRIGGER") == 2
        assert "AFTER INSERT ON invoice_line" in out
        assert "AFTER UPDATE ON invoice_line" in out
        # The UPDATE variant exposes both tables; the INSERT variant may not
        # declare OLD TABLE.
        insert_part = out[
            out.index("AFTER INSERT ON") - 400 : out.index("AFTER INSERT ON") + 200
        ]
        assert "OLD TABLE" not in insert_part

    def test_multi_event_row_trigger_joins_events_with_or(self) -> None:
        # Without transition tables a multi-event trigger is legal, but the
        # event list separator is OR in PostgreSQL, not a comma.
        sql = (
            "CREATE TRIGGER trg ON t AFTER INSERT, UPDATE AS BEGIN "
            "UPDATE x SET a = 1 WHERE id = 1 "
            "END"
        )
        out = self._t(sql)
        assert "INSERT, UPDATE" not in out

    def test_set_based_trigger_guards_against_recursive_firing(self) -> None:
        # T-SQL does not re-fire a trigger from its own statements
        # (RECURSIVE_TRIGGERS OFF by default); PostgreSQL always does, so a
        # set-based trigger that updates its own table recurses until the
        # stack limit (found on the live FE run). The emitted function must
        # bail out on nested firings.
        sql = (
            "CREATE TRIGGER trg_total ON invoice_line AFTER UPDATE AS BEGIN "
            "UPDATE il SET il.line_total = il.qty * il.unit_price "
            "FROM invoice_line il INNER JOIN inserted i ON i.id = il.id "
            "END"
        )
        out = self._t(sql)
        assert "pg_trigger_depth()" in out


class TestMySQLMultiEventTriggerSplit:
    """MySQL allows exactly one event per trigger: AFTER INSERT, UPDATE must
    become two triggers (found on the live FE run; MariaDB rejects the
    multi-event shell outright)."""

    def test_split_into_one_trigger_per_event(self) -> None:
        sql = (
            "CREATE TRIGGER trg ON t AFTER INSERT, UPDATE AS BEGIN "
            "UPDATE x SET a = 1 WHERE id = 1 "
            "END"
        )
        out = Transpiler().transpile(sql, source="tsql", target="mysql").sql
        assert "INSERT, UPDATE" not in out
        assert out.count("CREATE TRIGGER") == 2
        assert "AFTER INSERT ON t" in out
        assert "AFTER UPDATE ON t" in out


class TestMySQLRowAssignmentInTrigger:
    """MySQL BEFORE-trigger row assignment `SET NEW.col = expr` must survive.

    The parser read only a single identifier after SET, so `SET NEW.col = ...`
    mangled to `NEW := . col = ...` (found on the sakila-style compute trigger
    in the live FE run). It must become an assignment to the dotted target.
    """

    SQL = (
        "CREATE TRIGGER trg_c BEFORE INSERT ON invoice_line\n"
        "FOR EACH ROW\n"
        "BEGIN\n"
        "    SET NEW.line_total = NEW.qty * NEW.unit_price;\n"
        "END"
    )

    @staticmethod
    def _tight(sql: str) -> str:
        # Collapse the token-joiner's cosmetic spaces around '.' so the
        # assertion targets semantics, not whitespace.
        return re.sub(r"\s*\.\s*", ".", sql)

    def test_postgresql_assigns_dotted_target(self) -> None:
        out = Transpiler().transpile(self.SQL, "mysql", "postgresql").sql
        assert "NEW.line_total := NEW.qty * NEW.unit_price" in self._tight(out)
        assert "NEW :=" not in out
        assert ":= ." not in out

    def test_mysql_roundtrip_keeps_set(self) -> None:
        out = Transpiler().transpile(self.SQL, "mysql", "mysql").sql
        assert "SET NEW.line_total = NEW.qty * NEW.unit_price" in self._tight(out)


class TestPostgresTriggerToMySQL:
    """PostgreSQL splits trigger logic into a ``CREATE FUNCTION … RETURNS
    TRIGGER`` plus a ``CREATE TRIGGER … EXECUTE FUNCTION fn()`` binding. MySQL
    has neither a TRIGGER return type nor statement-level transition-table
    triggers, so both must degrade to a documented ``-- UNIQUE:`` carrier with a
    warning — never an invalid ``RETURNS TRIGGER`` or a mangled body (the
    postgresql→mysql pair of the 4×4 matrix). Same divergence already documented
    for T-SQL set-based triggers on MySQL."""

    FUNC = (
        "CREATE FUNCTION trg_touch_fn() RETURNS TRIGGER AS $$\n"
        "BEGIN\n"
        "    UPDATE invoice SET updated_at = CURRENT_TIMESTAMP\n"
        "    WHERE id IN (SELECT id FROM inserted);\n"
        "    RETURN NULL;\n"
        "END;\n$$ LANGUAGE plpgsql;"
    )

    BINDING = (
        "CREATE TRIGGER trg_touch AFTER UPDATE ON invoice\n"
        "REFERENCING NEW TABLE AS inserted\n"
        "FOR EACH STATEMENT EXECUTE FUNCTION trg_touch_fn();"
    )

    def _code(self, sql: str) -> str:
        # The executable text with UNIQUE carrier comments stripped.
        return "\n".join(
            line for line in sql.split("\n") if not line.strip().startswith("--")
        )

    def test_trigger_function_degrades_with_warning(self) -> None:
        r = Transpiler().transpile(self.FUNC, source="postgresql", target="mysql")
        # No invalid RETURNS TRIGGER in the executable output.
        assert "RETURNS TRIGGER" not in self._code(r.sql).upper()
        assert "UNIQUE:" in r.sql
        assert r.warnings or r.unsupported

    def test_trigger_binding_degrades_with_warning(self) -> None:
        r = Transpiler().transpile(self.BINDING, source="postgresql", target="mysql")
        code = self._code(r.sql).upper()
        # The old parser mangled EXECUTE FUNCTION into bogus DECLAREs.
        assert "DECLARE REFERENCING" not in code
        assert "DECLARE TABLE AS" not in code
        # No executable CREATE TRIGGER shell (MySQL cannot run this one).
        assert "EXECUTE FUNCTION" not in code
        assert "UNIQUE:" in r.sql
        assert r.warnings or r.unsupported

    def test_binding_roundtrips_to_postgresql(self) -> None:
        # pg->pg through the transpiler must keep the delegating binding valid.
        out = (
            Transpiler()
            .transpile(self.BINDING, source="postgresql", target="postgresql")
            .sql
        )
        assert "EXECUTE FUNCTION trg_touch_fn()" in out
        assert "AFTER UPDATE ON invoice" in out
