"""A non-catalog `IF EXISTS(...) BEGIN ... END` is control flow, not a guard.

The migration-guard path drops the `IF [NOT] EXISTS(<catalog query>)` condition
and transpiles only the guarded DDL (the catalog check has no target form). That
is wrong for a *real* condition: `IF EXISTS (SELECT NULL) BEGIN SELECT 2 END`
must not silently become `SELECT 2` (the guard — and its semantics — gone). It is
now routed to the procedural engine and preserved as a documented carrier with a
warning; a genuine system-catalog guard is still transpiled.
"""

from unique.core.transpiler import Transpiler

t = Transpiler()


class TestNonCatalogIfExists:
    def test_guard_not_silently_dropped(self) -> None:
        r = t.transpile(
            "if exists (select null)\nbegin\n  select 2\nend", "tsql", "oracle"
        )
        upper = r.sql.upper()
        # The dangerous old behaviour: the whole block collapsing to `SELECT 2`.
        assert "-- UNIQUE" in upper or "IF EXISTS" in upper, r.sql
        # The condition must survive in some form — not a bare guardless SELECT.
        assert not r.sql.strip().upper().startswith("SELECT 2"), r.sql
        # And the loss must be reported, never silent.
        assert r.warnings, "a carrier must carry a warning"

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
