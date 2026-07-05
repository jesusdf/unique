"""Assertion-hardening for column-definition flags and set-op/DISTINCT flags.

The mutation run showed these branches in convert.py were executed but not
verified (flipping a default flag survived): column nullability/PK/unique/
identity defaults, DISTINCT detection, and DROP without IF EXISTS. These tests
assert both the positive and the *default/negative* case so the mutants die.
"""

import sqlglot

from unique.core.transpiler import Transpiler

_READ = {"tsql": "tsql", "postgresql": "postgres", "mysql": "mysql", "oracle": "oracle"}


def _valid(sql: str, dialect: str) -> None:
    sqlglot.parse(sql, read=_READ[dialect], error_level=sqlglot.ErrorLevel.RAISE)


t = Transpiler()


class TestColumnFlags:
    def test_nullable_default_emits_no_not_null(self) -> None:
        # `a` is nullable (no NOT NULL); `b` is NOT NULL. Exactly one NOT NULL —
        # flipping the nullable default would wrongly add it to `a`.
        out = t.transpile(
            "CREATE TABLE tbl (a INT, b INT NOT NULL)", "tsql", "postgresql"
        ).sql
        assert out.upper().count("NOT NULL") == 1, out
        _valid(out, "postgresql")

    def test_primary_key_present_only_when_declared(self) -> None:
        with_pk = t.transpile(
            "CREATE TABLE tbl (a INT PRIMARY KEY, b INT)", "tsql", "postgresql"
        ).sql
        without_pk = t.transpile(
            "CREATE TABLE tbl (a INT, b INT)", "tsql", "postgresql"
        ).sql
        assert "PRIMARY KEY" in with_pk.upper()
        assert "PRIMARY KEY" not in without_pk.upper()

    def test_unique_present_only_when_declared(self) -> None:
        with_u = t.transpile(
            "CREATE TABLE tbl (a INT UNIQUE, b INT)", "tsql", "postgresql"
        ).sql
        without_u = t.transpile(
            "CREATE TABLE tbl (a INT, b INT)", "tsql", "postgresql"
        ).sql
        assert "UNIQUE" in with_u.upper()
        assert "UNIQUE" not in without_u.upper()

    def test_identity_present_only_when_declared(self) -> None:
        with_id = t.transpile(
            "CREATE TABLE tbl (a INT IDENTITY(1,1), b INT)", "tsql", "postgresql"
        ).sql
        without_id = t.transpile(
            "CREATE TABLE tbl (a INT, b INT)", "tsql", "postgresql"
        ).sql
        assert "SERIAL" in with_id.upper()  # T-SQL IDENTITY -> PostgreSQL SERIAL
        assert "SERIAL" not in without_id.upper()


class TestDistinct:
    def test_distinct_kept_and_absent(self) -> None:
        assert (
            "DISTINCT"
            in t.transpile("SELECT DISTINCT x FROM tbl", "tsql", "oracle").sql.upper()
        )
        assert (
            "DISTINCT"
            not in t.transpile("SELECT x FROM tbl", "tsql", "oracle").sql.upper()
        )


class TestDropGuard:
    def test_drop_is_idempotent(self) -> None:
        # DROP is emitted idempotently (DROP TABLE IF EXISTS) so a re-run script
        # does not error on an already-absent object.
        out = t.transpile("DROP TABLE tbl", "tsql", "postgresql").sql
        assert "DROP TABLE IF EXISTS" in out.upper()
        _valid(out, "postgresql")
