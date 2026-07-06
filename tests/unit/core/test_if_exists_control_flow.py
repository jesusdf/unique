"""A non-catalog `IF EXISTS(...) BEGIN ... END` is control flow, not a guard.

The migration-guard path drops the `IF [NOT] EXISTS(<catalog query>)` condition
and transpiles only the guarded DDL (the catalog check has no target form). That
is wrong for a *real* condition: `IF EXISTS (SELECT NULL FROM t) BEGIN … END`
must not silently lose the guard. On Oracle it is emulated — `IF EXISTS(subquery)`
is invalid PL/SQL (PLS-00204), so with no ELSE it becomes a cursor FOR loop over a
one-row probe (`FOR … IN (SELECT 1 FROM DUAL WHERE EXISTS (subquery)) LOOP … END
LOOP`): the body runs once iff the subquery returns a row. A genuine system-catalog
guard is still transpiled (condition dropped, DDL emitted). Validated live.
"""

from unique.core.transpiler import Transpiler

t = Transpiler()


class TestNonCatalogIfExists:
    def test_if_exists_emulated_as_for_loop(self) -> None:
        # A real-data IF EXISTS with a valid body (a migration guard).
        r = t.transpile(
            "IF EXISTS (SELECT NULL FROM dbo.h_versionbd WHERE revision = 8254)\n"
            "BEGIN\n  PRINT 'already applied'\nEND",
            "tsql",
            "oracle",
        )
        up = r.sql.upper()
        # The EXISTS condition survives — emulated as a cursor FOR-loop probe,
        # never silently collapsed to a bare, guardless body.
        assert "FOR " in up and "WHERE EXISTS" in up and "LOOP" in up, r.sql
        assert "DBMS_OUTPUT.PUT_LINE" in up, r.sql
        # It is a real translation (not a carrier), so the invalid `IF EXISTS …
        # THEN` form must not appear.
        assert "IF EXISTS" not in up, r.sql

    def test_if_exists_else_becomes_two_for_loops(self) -> None:
        # An ELSE is a second FOR over the *negated* probe — EXISTS and NOT EXISTS
        # are mutually exclusive, so exactly one loop body fires.
        r = t.transpile(
            "IF EXISTS (SELECT NULL FROM dbo.t WHERE c = 1)\n"
            "  BEGIN PRINT 'a' END\n"
            "ELSE\n"
            "  BEGIN PRINT 'b' END",
            "tsql",
            "oracle",
        )
        up = r.sql.upper()
        assert up.count("FOR ") == 2 and up.count("LOOP") == 4, r.sql  # 2 FOR…LOOP
        assert "WHERE EXISTS" in up and "WHERE NOT EXISTS" in up, r.sql
        assert "IF EXISTS" not in up, r.sql

    def test_if_not_exists_else_negation_flips(self) -> None:
        # IF NOT EXISTS … ELSE: the THEN probe is NOT EXISTS, the ELSE probe EXISTS.
        r = t.transpile(
            "IF NOT EXISTS (SELECT NULL FROM dbo.t WHERE c = 1)\n"
            "  BEGIN PRINT 'a' END ELSE BEGIN PRINT 'b' END",
            "tsql",
            "oracle",
        )
        import re

        probes = re.findall(r"WHERE\s+(NOT\s+)?EXISTS", r.sql.upper())
        # THEN loop first (NOT EXISTS), then ELSE loop (bare EXISTS).
        assert [bool(p.strip()) for p in probes] == [True, False], r.sql

    def test_set_noexec_carried_and_not_merged(self) -> None:
        # A migration guard: PRINT + `SET NOEXEC ON` (a session option with no
        # Oracle equivalent). PRINT must not absorb the following SET, and the
        # SET is a documented carrier with a warning.
        r = t.transpile(
            "IF EXISTS (SELECT NULL FROM dbo.h_versionbd WHERE revision = 8254)\n"
            "BEGIN\n  PRINT 'skip'\n  SET NOEXEC ON\nEND",
            "tsql",
            "oracle",
        )
        up = r.sql.upper()
        assert "NOEXEC" in up and "UNIQUE:" in up, r.sql  # carried, not executed
        assert "PUT_LINE('SKIP')" in up.replace(" ", ""), r.sql  # not merged
        assert any("NOEXEC" in w.message for w in r.warnings), r.warnings

    def test_catalog_guard_still_transpiles_body(self) -> None:
        # A genuine idempotent-DDL guard (system catalog) keeps its old behaviour:
        # drop the catalog check, transpile the guarded CREATE.
        r = t.transpile(
            "IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 't') "
            "BEGIN CREATE TABLE t (a INT) END",
            "tsql",
            "oracle",
        )
        assert "CREATE TABLE" in r.sql.upper(), r.sql
        assert "SYS.TABLES" not in r.sql.upper(), r.sql
