"""T-SQL assignment-select vs Oracle SELECT INTO (audit 2026-07-02, S2-3).

``SELECT @v = col FROM ...`` leaves ``@v`` unchanged when no row matches;
Oracle's ``SELECT INTO`` raises NO_DATA_FOUND instead, making any following
``IF v IS NULL`` guard unreachable. The Oracle emitter must wrap converted
assignment-selects in a NO_DATA_FOUND handler that preserves T-SQL semantics.
"""

from unique.core.transpiler import Transpiler

PROC = (
    "CREATE PROCEDURE dbo.p @id INT AS BEGIN "
    "DECLARE @old DECIMAL(10,2); "
    "SELECT @old = price FROM products WHERE id = @id; "
    "IF @old IS NULL BEGIN PRINT 'missing'; END "
    "END"
)

NATIVE_ORACLE = (
    "CREATE OR REPLACE PROCEDURE p (v_id IN NUMBER) IS "
    "v_old NUMBER; "
    "BEGIN "
    "SELECT price INTO v_old FROM products WHERE id = v_id; "
    "END;"
)


class TestNoDataFoundDivergence:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_tsql_assignment_select_wrapped_for_oracle(self) -> None:
        out = self.t.transpile(PROC, "tsql", "oracle").sql
        assert "SELECT price INTO V_OLD" in out
        assert "WHEN NO_DATA_FOUND" in out
        # The IS NULL guard must remain reachable.
        assert "IF V_OLD IS NULL" in out

    def test_native_oracle_select_into_not_wrapped(self) -> None:
        # An Oracle-native SELECT INTO keeps its raising behavior: adding a
        # handler would silently change the source program's semantics.
        out = self.t.transpile(NATIVE_ORACLE, "oracle", "oracle").sql
        assert out.count("NO_DATA_FOUND") == 0

    def test_tsql_assignment_select_to_postgresql_unchanged(self) -> None:
        # PL/pgSQL SELECT INTO already leaves the variable NULL on no rows —
        # same observable behavior as T-SQL for a fresh variable; no wrapper.
        out = self.t.transpile(PROC, "tsql", "postgresql").sql
        assert "NO_DATA_FOUND" not in out
        assert "INTO v_old" in out.replace("V_OLD", "v_old")
