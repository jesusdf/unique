# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Guard-translation matrix (audit 2026-07-08, M2 — clears A1/A3/N1).

The 2026-07-08 audit showed the guard recognizers matched exactly one spelling
each: a leading comment, a ``BEGIN…END`` wrapper, or a missing ``BEGIN``
flipped a batch into the comment-out fallback (or silently dropped the
condition). Per the circuit-breaker rules these tests pin the *combinatorial
neighbors* of every fixed shape, not just the reproduced one.
"""

from __future__ import annotations

import re

import pytest

from unique.core.transpiler import Transpiler


def _executable(sql: str) -> str:
    """The non-comment lines of an output (what the target would run)."""
    return "\n".join(
        line
        for line in sql.splitlines()
        if line.strip() and not line.strip().startswith("--")
    )


BLOCK_COMMENT = "/* ---- section header ---- */\n"
LINE_COMMENT = "-- section header\n"


class TestDropGuardWithLeadingTrivia:
    """A1: a comment prefix must not defeat guard extraction."""

    @pytest.mark.parametrize("trivia", ["", LINE_COMMENT, BLOCK_COMMENT])
    @pytest.mark.parametrize("target", ["postgresql", "mysql"])
    def test_object_id_drop_guard_translates(self, trivia: str, target: str) -> None:
        src = (
            f"{trivia}IF OBJECT_ID('dbo.my_func', 'FN') IS NOT NULL\n"
            "    DROP FUNCTION dbo.my_func\nGO\n"
        )
        out = Transpiler().transpile(src, "tsql", target)
        assert "DROP FUNCTION IF EXISTS my_func" in out.sql
        assert "OBJECT_ID" not in _executable(out.sql)

    @pytest.mark.parametrize("trivia", [LINE_COMMENT, BLOCK_COMMENT])
    def test_object_id_drop_guard_translates_oracle(self, trivia: str) -> None:
        src = (
            f"{trivia}IF OBJECT_ID('dbo.my_func', 'FN') IS NOT NULL\n"
            "    DROP FUNCTION dbo.my_func\nGO\n"
        )
        out = (
            Transpiler().transpile(src, "oracle", "oracle")
            if False
            else (Transpiler().transpile(src, "tsql", "oracle"))
        )
        assert "EXECUTE IMMEDIATE 'DROP FUNCTION my_func'" in out.sql

    @pytest.mark.parametrize("trivia", [LINE_COMMENT, BLOCK_COMMENT])
    def test_comment_survives_next_to_the_translation(self, trivia: str) -> None:
        src = (
            f"{trivia}IF OBJECT_ID('dbo.my_func', 'FN') IS NOT NULL\n"
            "    DROP FUNCTION dbo.my_func\nGO\n"
        )
        out = Transpiler().transpile(src, "tsql", "postgresql")
        assert "section header" in out.sql


class TestOracleSlashAfterGuardBlock:
    """A3: a leading comment must not suppress the '/' block terminator."""

    @pytest.mark.parametrize("trivia", ["", LINE_COMMENT, BLOCK_COMMENT])
    def test_data_guard_block_keeps_slash_before_next_batch(self, trivia: str) -> None:
        src = (
            f"{trivia}IF NOT EXISTS (SELECT 1 FROM h_x WHERE lang = 'ar')\n"
            "BEGIN\n    INSERT INTO h_x (lang) VALUES ('ar');\nEND\nGO\n"
            "SELECT 1;\nGO\n"
        )
        out = Transpiler().transpile(src, "tsql", "oracle").sql
        block_end = out.index("END LOOP; END;")
        next_stmt = out.index("SELECT 1", block_end)
        between = out[block_end:next_stmt]
        assert "\n/" in between, f"missing '/' terminator; got: {between!r}"


class TestDataGuardWithoutBegin:
    """N1: an unbracketed real-data guard must never lose its condition."""

    BODIES = {
        "insert": "INSERT INTO cfg (k) VALUES ('x')",
        "update": "UPDATE cfg SET v = 1 WHERE k = 'y'",
        "delete": "DELETE FROM cfg WHERE k = 'x'",
    }

    @pytest.mark.parametrize("body", sorted(BODIES))
    @pytest.mark.parametrize("target", ["postgresql", "oracle", "mysql"])
    def test_condition_is_never_silently_dropped(self, body: str, target: str) -> None:
        src = (
            "IF NOT EXISTS (SELECT 1 FROM cfg WHERE k = 'x')\n"
            f"    {self.BODIES[body]};\nGO\n"
        )
        out = Transpiler().transpile(src, "tsql", target)
        executable = _executable(out.sql)
        if self.BODIES[body].split()[0] in executable:
            # The statement shipped executable: its guard must too.
            assert (
                "NOT EXISTS" in executable
            ), f"{target}/{body}: condition dropped:\n{out.sql}"
        else:
            # Degraded: must be signalled, never silent.
            assert out.warnings or out.unsupported

    def test_pg_form_is_runnable_do_block(self) -> None:
        src = (
            "IF NOT EXISTS (SELECT 1 FROM cfg WHERE k = 'x')\n"
            "    INSERT INTO cfg (k) VALUES ('x');\nGO\n"
        )
        out = Transpiler().transpile(src, "tsql", "postgresql").sql
        assert "DO $$" in out and "NOT EXISTS" in out and "INSERT INTO cfg" in out


class TestHonestFallbackLabel:
    """M1 residue: the comment-out fallback must not claim 'SET option'."""

    def test_non_set_batch_gets_honest_signal(self) -> None:
        # An IF-guard shape no recognizer handles: condition over OBJECT_ID
        # with an EXEC body. It may degrade — but never labelled a SET option,
        # and never without an unsupported entry.
        src = "IF OBJECT_ID('dbo.x') IS NOT NULL\n    EXEC dbo.some_proc\nGO\n"
        out = Transpiler().transpile(src, "tsql", "postgresql")
        if "EXEC" not in _executable(out.sql) and "CALL" not in _executable(out.sql):
            set_mislabels = [
                w
                for w in out.warnings
                if w.feature == "set_option" and "IF OBJECT_ID" in w.message
            ]
            assert not set_mislabels, "guard batch mislabelled as SET option"
            assert out.unsupported, "batch commented out with no unsupported entry"


class TestBeginWrappedCatalogGuards:
    """A2: the BEGIN…END-wrapped spelling (what SSMS generates) must translate
    exactly like the unbracketed one — for every head form and body kind."""

    @pytest.mark.parametrize(
        "head",
        [
            "IF OBJECT_ID('s1.t1') IS NOT NULL",
            "IF EXISTS (SELECT * FROM sys.objects "
            "WHERE object_id = OBJECT_ID('s1.t1'))",
        ],
    )
    @pytest.mark.parametrize("target", ["postgresql", "mysql"])
    def test_wrapped_drop_guard_translates(self, head: str, target: str) -> None:
        src = f"{head}\nBEGIN\n    DROP TABLE [s1].[t1]\nEND\nGO\n"
        out = Transpiler().transpile(src, "tsql", target)
        assert "DROP TABLE IF EXISTS" in out.sql, out.sql
        assert "OBJECT_ID" not in _executable(out.sql)

    def test_wrapped_drop_guard_translates_oracle(self) -> None:
        src = (
            "IF OBJECT_ID('s1.t1') IS NOT NULL\n"
            "BEGIN\n    DROP TABLE [s1].[t1]\nEND\nGO\n"
        )
        out = Transpiler().transpile(src, "tsql", "oracle")
        # The schema qualifier is kept (only the T-SQL default 'dbo.' is noise).
        assert "EXECUTE IMMEDIATE 'DROP TABLE s1.t1'" in out.sql, out.sql

    @pytest.mark.parametrize("trivia", ["", LINE_COMMENT, BLOCK_COMMENT])
    def test_wrapped_create_guard_translates(self, trivia: str) -> None:
        src = (
            f"{trivia}IF OBJECT_ID('s1.t1') IS NULL\n"
            "BEGIN\n    CREATE TABLE [s1].[t1] ([id] [int] NOT NULL)\nEND\nGO\n"
        )
        out = Transpiler().transpile(src, "tsql", "oracle")
        assert "EXECUTE IMMEDIATE" in out.sql and "user_objects" in out.sql, out.sql


class TestGuardIdempotencyOnNativeTargets:
    """A5: a catalog CREATE-guard must keep its re-runnable intent where the
    target has a native form (CREATE TABLE IF NOT EXISTS), not drop it."""

    SRC = (
        "IF NOT EXISTS (SELECT * FROM sys.objects "
        "WHERE object_id = OBJECT_ID('s1.t1'))\n"
        "BEGIN\n    CREATE TABLE [s1].[t1] ([id] [int] NOT NULL)\nEND\nGO\n"
    )

    @pytest.mark.parametrize("target", ["postgresql", "mysql"])
    def test_create_table_guard_stays_idempotent(self, target: str) -> None:
        out = Transpiler().transpile(self.SRC, "tsql", target)
        assert "CREATE TABLE IF NOT EXISTS" in out.sql, out.sql

    def test_unbracketed_form_too(self) -> None:
        src = (
            "IF OBJECT_ID('s1.t1') IS NULL\n"
            "    CREATE TABLE [s1].[t1] ([id] [int] NOT NULL)\nGO\n"
        )
        out = Transpiler().transpile(src, "tsql", "postgresql")
        assert "CREATE TABLE IF NOT EXISTS" in out.sql, out.sql


class TestUuidFunctionInsideProceduralBodies:
    """A4: NEWID() inside a guard/routine body must map per target — sqlglot
    canonicalizes it to UUID(), which only exists on MySQL."""

    SRC = (
        "IF NOT EXISTS (SELECT 1 FROM h_x WHERE lang = 'ar')\n"
        "BEGIN\n    INSERT INTO h_x (id, lang) VALUES (NEWID(), 'ar');\nEND\nGO\n"
    )

    @pytest.mark.parametrize(
        ("target", "spelling"),
        [
            ("oracle", "SYS_GUID()"),
            ("postgresql", "GEN_RANDOM_UUID()"),
            ("mysql", "UUID()"),
        ],
    )
    def test_guarded_newid_maps_per_target(self, target: str, spelling: str) -> None:
        out = Transpiler().transpile(self.SRC, "tsql", target)
        assert spelling.lower() in out.sql.lower(), out.sql
        if target != "mysql":
            assert "UUID()" not in out.sql.upper().replace(
                spelling.upper(), ""
            ), out.sql


class TestTrailingCommentOnGuardLine:
    """Trivia between the condition and the body (e.g. '-- old name' on the
    guard line) must not defeat the DROP matcher nor be lost."""

    SRC = (
        "IF OBJECT_ID('dbo.trg_x', 'TR') IS NOT NULL   -- old name\n"
        "    DROP TRIGGER dbo.trg_x\nGO\n"
    )

    def test_drop_still_recognized(self) -> None:
        out = Transpiler().transpile(self.SRC, "tsql", "postgresql")
        # PG resolves the trigger's table from the catalog (DO block), never a
        # bare schema-qualified DROP TRIGGER without ON.
        assert "pg_trigger" in out.sql, out.sql
        assert "DROP TRIGGER IF EXISTS dbo." not in out.sql

    def test_comment_preserved(self) -> None:
        out = Transpiler().transpile(self.SRC, "tsql", "postgresql")
        assert "old name" in out.sql


class TestUnmappableGuardBodyWarns:
    """A catalog guard whose body has no native conditional form (e.g.
    ``ALTER TABLE … ADD DEFAULT``) must never lose its guard silently
    (no-silent-loss; user report 2026-07-09)."""

    _SRC = (
        "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE [object_id] = "
        "OBJECT_ID('s1.t1') AND [name] = 'c1' AND default_object_id <> 0)\n"
        "BEGIN\n"
        "ALTER TABLE [s1].[t1] ADD DEFAULT ((0)) FOR [c1]\n"
        "END\nGO"
    )

    @pytest.mark.parametrize("target", ["postgresql", "mysql", "oracle"])
    def test_add_default_guard_drop_is_warned(self, target: str) -> None:
        result = Transpiler().transpile(self._SRC, source="tsql", target=target)
        # The DDL itself survives, executable (not a carrier)...
        assert "UNIQUE:" not in result.sql
        assert re.search(r"(?i)ALTER TABLE", result.sql)
        assert "DEFAULT" in result.sql.upper()
        # ...and the dropped condition is reported, not silent.
        assert any(
            w.feature == "guard_dropped" for w in result.warnings
        ), result.warnings

    def test_present_polarity_non_drop_body_also_warned(self) -> None:
        src = (
            "IF EXISTS (SELECT 1 FROM sys.columns WHERE [object_id] = "
            "OBJECT_ID('s1.t1') AND [name] = 'c1')\n"
            "BEGIN\n"
            "ALTER TABLE [s1].[t1] ALTER COLUMN [c1] INT NOT NULL\n"
            "END\nGO"
        )
        result = Transpiler().transpile(src, source="tsql", target="postgresql")
        assert any(w.feature == "guard_dropped" for w in result.warnings)
