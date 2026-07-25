"""B11/N10: constant dynamic-SQL strings are transpiled, not shipped verbatim.

A *constant* SQL string reaching an ``EXEC`` / ``sp_executesql`` /
``EXECUTE`` / ``EXECUTE IMMEDIATE`` sink — either as a literal argument or via a
variable whose value is a single constant literal — is routed through the real
transpiler pipeline and the translation is spliced back. A non-constant variable
or a string that does not parse as SQL is left alone but flagged with a
"review dynamic SQL" warning, so no untranslated executable string is ever
shipped silently (the no-silent-loss invariant, one quote-level down).
"""

import sqlglot

from unique.core.transpiler import Transpiler

t = Transpiler()

_SQLGLOT_DIALECT = {
    "postgresql": "postgres",
    "oracle": "oracle",
    "mysql": "mysql",
    "tsql": "tsql",
}


def _target_parse(sql: str, target: str) -> None:
    """Cheap validity gate: the emitted routine must parse in the target."""
    sqlglot.parse(
        sql, read=_SQLGLOT_DIALECT[target], error_level=sqlglot.ErrorLevel.RAISE
    )


# A constant SQL string carried by a variable (the N10 variable form).
_PROC_VAR = (
    "CREATE PROCEDURE run_dyn AS\n"
    "BEGIN\n"
    "  DECLARE @sql NVARCHAR(MAX) = "
    "N'SELECT TOP 5 name, GETDATE() AS d FROM users ORDER BY name';\n"
    "  EXEC sp_executesql @sql;\n"
    "END"
)

# The same constant passed as a literal argument (the N10 literal form).
_PROC_LITERAL = (
    "CREATE PROCEDURE run_dyn AS\n"
    "BEGIN\n"
    "  EXEC('SELECT TOP 5 name, GETDATE() AS d FROM users ORDER BY name');\n"
    "END"
)

_TARGET_LIMITER = {
    "postgresql": "LIMIT 5",
    "oracle": "FETCH",  # FETCH FIRST 5 ROWS ONLY
}


class TestConstantDynamicSqlTranslated:
    """The executed SQL text is translated to the target dialect."""

    def _check(self, src: str, target: str) -> str:
        out = t.transpile(src, "tsql", target).sql
        up = out.upper()
        assert "TOP" not in up, out  # source limiter idiom is gone
        assert "GETDATE" not in up, out  # source scalar idiom is gone
        assert _TARGET_LIMITER[target] in up, out  # target limiter idiom present
        if target != "oracle":
            # sqlglot cannot parse a PL/SQL routine body (the ``/``
            # terminator); Oracle validity is covered by the live probes.
            _target_parse(out, target)
        return out

    def test_variable_form_postgresql(self) -> None:
        self._check(_PROC_VAR, "postgresql")

    def test_variable_form_oracle(self) -> None:
        self._check(_PROC_VAR, "oracle")

    def test_literal_form_postgresql(self) -> None:
        self._check(_PROC_LITERAL, "postgresql")

    def test_literal_form_oracle(self) -> None:
        self._check(_PROC_LITERAL, "oracle")

    def test_dynamic_stays_dynamic(self) -> None:
        # The run stays a dynamic-SQL execution (EXECUTE / EXECUTE IMMEDIATE),
        # only its string content is translated — not unwrapped into a bare
        # statement (a bare SELECT has no destination in plpgsql).
        out = t.transpile(_PROC_VAR, "tsql", "postgresql").sql
        assert "EXECUTE" in out.upper(), out


class TestNonConstantWarns:
    """A non-constant variable or a non-SQL string is flagged, never silently
    shipped untranslated."""

    def test_nonconstant_variable_warns(self) -> None:
        src = (
            "CREATE PROCEDURE p AS\n"
            "BEGIN\n"
            "  DECLARE @sql NVARCHAR(MAX) = N'SELECT 1 AS x';\n"
            "  SET @sql = @sql + N' FROM t';\n"  # second assignment -> non-constant
            "  EXEC sp_executesql @sql;\n"
            "END"
        )
        res = t.transpile(src, "tsql", "postgresql")
        msgs = " ".join(w.message.lower() for w in res.warnings)
        assert "dynamic sql" in msgs, res.warnings

    def test_non_sql_string_warns_and_is_unchanged(self) -> None:
        src = "CREATE PROCEDURE p AS\nBEGIN\n  EXEC('hello');\nEND"
        res = t.transpile(src, "tsql", "postgresql")
        msgs = " ".join(w.message.lower() for w in res.warnings)
        assert "dynamic sql" in msgs, res.warnings
        # The non-SQL string content is left untouched (nothing to translate).
        assert "hello" in res.sql, res.sql

    def test_parameterized_sink_keeps_placeholder_handling(self) -> None:
        # A binds-bearing sink (USING / sp_executesql bindings) keeps the
        # established emit-time placeholder machinery: the $1 placeholder must
        # become MySQL's ?, not be statically re-translated into the string.
        src = (
            "CREATE OR REPLACE FUNCTION f() RETURNS void LANGUAGE plpgsql "
            "AS $$\nBEGIN\n"
            "  EXECUTE 'INSERT INTO t VALUES ($1)' USING 5;\n"
            "END;\n$$;"
        )
        out = t.transpile(src, "postgresql", "mysql").sql
        assert "VALUES (?)" in out, out
        assert "$1" not in out, out


class TestRoundTrip:
    def test_constant_dynamic_sql_round_trips(self) -> None:
        a_b = t.transpile(_PROC_VAR, "tsql", "postgresql").sql
        b_a = t.transpile(a_b, "postgresql", "tsql").sql
        up = b_a.upper()
        assert "TOP 5" in up, b_a  # source idiom restored
        assert "GETDATE" in up, b_a
        assert "LIMIT" not in up, b_a  # intermediate idiom gone


class TestRecursionCap:
    def test_depth_cap_warns(self) -> None:
        from unique.core.procedural.transformer import base as tbase
        from unique.core.procedural.transformer.base import ProceduralTransformer

        tr = ProceduralTransformer("tsql", "postgresql")
        token = tbase._EMBEDDED_DYN_SQL_DEPTH.set(tbase._MAX_EMBEDDED_DYN_SQL_DEPTH)
        try:
            assert tr._translate_dynamic_sql_text("SELECT 1 AS x") is None
        finally:
            tbase._EMBEDDED_DYN_SQL_DEPTH.reset(token)
        msgs = " ".join(tr._warnings).lower()
        assert "dynamic sql" in msgs and "deep" in msgs, tr._warnings
