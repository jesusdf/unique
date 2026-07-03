"""THROW/RAISERROR message preservation (audit 2026-07-02, S2-2).

``THROW 50001, 'not found', 1`` must keep the human-readable message on every
target; v0.7.0 used the error *number* as the message and silently dropped
the text.
"""

from unique.core.transpiler import Transpiler

PROC_THROW = "CREATE PROCEDURE dbo.p AS BEGIN " "THROW 50001, 'not found', 1; " "END"

PROC_RAISERROR = (
    "CREATE PROCEDURE dbo.p AS BEGIN " "RAISERROR('bad input', 16, 1); " "END"
)


class TestThrowMessagePreserved:
    def setup_method(self) -> None:
        self.t = Transpiler()

    def test_postgresql_keeps_text(self) -> None:
        out = self.t.transpile(PROC_THROW, "tsql", "postgresql").sql
        assert "'not found'" in out
        assert "RAISE EXCEPTION" in out
        # The number must not be used as the message.
        assert "RAISE EXCEPTION '%', 50001" not in out

    def test_oracle_keeps_text_and_maps_number(self) -> None:
        out = self.t.transpile(PROC_THROW, "tsql", "oracle").sql
        assert "RAISE_APPLICATION_ERROR(-20001, 'not found')" in out

    def test_mysql_keeps_text_and_number(self) -> None:
        out = self.t.transpile(PROC_THROW, "tsql", "mysql").sql
        assert "MESSAGE_TEXT = 'not found'" in out
        assert "MYSQL_ERRNO = 50001" in out

    def test_raiserror_text_form(self) -> None:
        for target, needle in [
            ("postgresql", "'bad input'"),
            ("oracle", "RAISE_APPLICATION_ERROR(-20001, 'bad input')"),
            ("mysql", "MESSAGE_TEXT = 'bad input'"),
        ]:
            out = self.t.transpile(PROC_RAISERROR, "tsql", target).sql
            assert needle in out, f"{target}: {out}"
