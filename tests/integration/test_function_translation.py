# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Function-translation audit for standalone DML.

sqlglot models most specialized functions with their arguments in *named slots*
(Substring -> this/start/length, Replace -> this/expression/replacement, ...),
not in ``expressions``. The converter previously read only ``this`` +
``expressions``, so every named slot was dropped: ``SUBSTRING(a, 1, 3)`` became
``SUBSTR(a)``. These tests pin that all arguments survive, across engines.
"""

from __future__ import annotations

import re

import pytest

from tests.helpers.validity import assert_translated, executable_body, executable_lines
from unique.core.procedural.transformer import ProceduralTransformer
from unique.core.transpiler import Transpiler

_TARGETS = ("oracle", "postgresql", "mysql")


def _ir(source: str, target: str, fragment: str) -> str | None:
    """Run one scalar/DML fragment through the procedural IR-first pipeline
    directly (bypassing the routine-shell parser) — the same helper pattern
    as ``tests/unit/core/test_ir_first_families.py``, used here to probe the
    procedural pipeline's function mapping independently of the standalone
    DML pipeline (dual-pipeline symmetry rule)."""
    return ProceduralTransformer(source, target)._ir_transpile_dml(fragment)


def _t(sql: str, target: str, source: str = "tsql") -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


def _expr(out: str) -> str:
    """The select-list expression, whitespace-normalized."""
    head = out.split("FROM")[0]
    head = re.sub(r"(?i)^\s*SELECT\s+", "", head)
    return re.sub(r"\s+", " ", head).strip()


class TestArgumentsPreserved:
    """No argument may be dropped on the way through the IR."""

    @pytest.mark.parametrize("target", _TARGETS)
    def test_substring_keeps_three_args(self, target: str) -> None:
        out = _expr(_t("SELECT SUBSTRING(a, 1, 3) FROM t", target))
        assert "1" in out and "3" in out and "a" in out
        assert out.count(",") == 2
        expected = {
            "oracle": "SUBSTR(",
            "mysql": "SUBSTRING(",
            "postgresql": "SUBSTRING(",
        }[target]
        assert out.upper().startswith(expected), out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_replace_keeps_three_args(self, target: str) -> None:
        out = _expr(_t("SELECT REPLACE(a, 'x', 'y') FROM t", target))
        assert "'x'" in out and "'y'" in out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_round_keeps_precision(self, target: str) -> None:
        out = _expr(_t("SELECT ROUND(a, 2) FROM t", target))
        assert "2" in out and out.count(",") == 1

    @pytest.mark.parametrize("target", _TARGETS)
    def test_stuff_keeps_four_args(self, target: str) -> None:
        # Full output (not _expr): PostgreSQL's OVERLAY(... FROM 1 FOR 2) rewrite
        # contains a FROM that the naive expr-splitter would cut on.
        out = _t("SELECT STUFF(a, 1, 2, 'xy') FROM t", target)
        assert "1" in out and "2" in out and "'xy'" in out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_replicate_keeps_count(self, target: str) -> None:
        out = _expr(_t("SELECT REPLICATE('x', 5) FROM t", target))
        assert "5" in out
        assert out.upper().startswith(("REPEAT(", "RPAD(", "REPLICATE(")), out
        if target in ("mysql", "postgresql"):
            assert "REPLICATE" not in out.upper(), out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_dateadd_keeps_all_args(self, target: str) -> None:
        out = _expr(_t("SELECT DATEADD(day, 1, a) FROM t", target))
        assert "1" in out and "a" in out
        expected = {
            "oracle": "a + NUMTODSINTERVAL(1, 'DAY')",
            "mysql": "DATE_ADD(a, INTERVAL 1 DAY)",
            "postgresql": "a + INTERVAL '1 DAY'",
        }[target]
        assert out == expected, out

    @pytest.mark.parametrize("target", _TARGETS)
    def test_coalesce_variadic(self, target: str) -> None:
        out = _expr(_t("SELECT COALESCE(a, b, 0) FROM t", target))
        assert out.upper().startswith("COALESCE(")
        assert out.count(",") == 2

    @pytest.mark.parametrize("target", _TARGETS)
    def test_concat_variadic(self, target: str) -> None:
        out = _expr(_t("SELECT CONCAT(a, b, c) FROM t", target))
        assert out.count(",") == 2


class TestUnmappedFunctionNamePreserved:
    """A function with no direct equivalent keeps its original name rather than
    degrading to the internal ``ANONYMOUS`` placeholder, so the output is
    reviewable SQL rather than something obviously broken."""

    @pytest.mark.parametrize(
        "fn",
        ["PATINDEX('%x%', a)", "CHOOSE(2, 'a', 'b')", "STR(1.5, 6, 2)"],
    )
    @pytest.mark.parametrize("target", _TARGETS)
    def test_name_not_anonymous(self, fn: str, target: str) -> None:
        out = _t(f"SELECT {fn} FROM t", target)
        assert "ANONYMOUS" not in out.upper()
        assert fn.split("(")[0] in out.upper()


class TestKnownGoodMappings:
    """Spot-check functions that do have clean cross-engine mappings."""

    def test_getutcdate_maps_to_utc_timestamp_on_mysql(self) -> None:
        # Shared pair map (PROCEDURAL_FUNC_MAPS) consumed by the IR too
        # (M3-final): GETUTCDATE is no longer an unmapped passthrough.
        out = _t("SELECT GETUTCDATE() FROM t", "mysql")
        assert "UTC_TIMESTAMP" in out.upper()
        assert "GETUTCDATE" not in out.upper()

    def test_charindex_to_instr_oracle(self) -> None:
        out = _t("SELECT CHARINDEX('x', a) FROM t", "oracle")
        assert_translated(
            out, "oracle", present=("INSTR(a, 'x')",), absent=("CHARINDEX",)
        )

    def test_isnull_to_coalesce(self) -> None:
        for target in _TARGETS:
            out = _t("SELECT ISNULL(a, 0) FROM t", target)
            assert_translated(
                out, target, present=("COALESCE(a, 0)",), absent=("ISNULL",)
            )

    def test_newid_to_uuid(self) -> None:
        out = _t("SELECT NEWID() FROM t", "postgresql")
        assert_translated(
            out, "postgresql", present=("gen_random_uuid()",), absent=("NEWID",)
        )


class TestConditionalFunction:
    """MySQL IF() / T-SQL IIF() translate to each target's conditional.

    Found on the sakila views: IF(cu.active, ...) leaked verbatim into
    T-SQL/PostgreSQL/Oracle output, where no such function exists.
    """

    @pytest.mark.parametrize(
        "source,expr",
        [("mysql", "IF(a > 0, 'y', 'n')"), ("tsql", "IIF(a > 0, 'y', 'n')")],
    )
    @pytest.mark.parametrize("target", ("tsql", "oracle", "postgresql", "mysql"))
    def test_conditional_translated(self, source: str, expr: str, target: str) -> None:
        if source == target:
            pytest.skip("same-dialect passthrough")
        out = Transpiler().transpile(f"SELECT {expr} FROM t;", source, target).sql
        idiom = {
            "tsql": "IIF(",
            "mysql": "IF(",
            "oracle": "CASE WHEN",
            "postgresql": "CASE WHEN",
        }[target]
        absent = {
            "tsql": ("IF(",),  # IIF( contains IF( — checked via idiom below
            "mysql": ("IIF(", "CASE WHEN"),
            "oracle": ("IIF(", "IF("),
            "postgresql": ("IIF(", "IF("),
        }[target]
        assert_translated(out, target, present=(idiom, "'y'", "'n'"))
        body = executable_lines(out).upper()
        for needle in absent:
            if target == "tsql" and needle == "IF(":
                # IIF( legitimately contains IF(; ensure no bare IF( remains.
                assert not re.search(r"(?<!I)\bIF\(", body), out
            else:
                assert needle not in body, out


class TestMysqlUnixTimestampToPostgresql:
    """B36b: MySQL UNIX_TIMESTAMP()/UNIX_TIMESTAMP(expr) was an untranslated
    built-in leak (UNIQUE-1151) into PostgreSQL. EXTRACT(EPOCH FROM ...)
    matches value-for-value (live-verified against MySQL 8 / PostgreSQL 16 in
    UTC): UNIX_TIMESTAMP('2020-01-01 00:00:00') = 1577836800 =
    EXTRACT(EPOCH FROM TIMESTAMP '2020-01-01 00:00:00'), and a fractional
    argument round-trips exactly (…00.500 on both sides).
    """

    def test_with_arg_translates_to_extract_epoch(self) -> None:
        out = _t("SELECT UNIX_TIMESTAMP(a) FROM t", "postgresql", source="mysql")
        assert_translated(
            out,
            "postgresql",
            present=("EXTRACT(EPOCH FROM a)",),
            absent=("UNIX_TIMESTAMP",),
        )

    def test_literal_datetime_arg_value_form(self) -> None:
        out = _t(
            "SELECT UNIX_TIMESTAMP('2020-01-01 00:00:00')",
            "postgresql",
            source="mysql",
        )
        assert_translated(
            out,
            "postgresql",
            present=("EXTRACT(EPOCH FROM '2020-01-01 00:00:00')",),
            absent=("UNIX_TIMESTAMP",),
        )

    def test_no_arg_floors_to_whole_seconds(self) -> None:
        # MySQL's niladic form has whole-second resolution (it reads NOW(),
        # which MySQL has no fractional seconds for); PostgreSQL's
        # CURRENT_TIMESTAMP carries microseconds, so a bare EXTRACT would
        # silently gain sub-second precision MySQL never has. FLOOR matches
        # MySQL's own granularity.
        out = _t("SELECT UNIX_TIMESTAMP()", "postgresql", source="mysql")
        assert_translated(
            out,
            "postgresql",
            present=("FLOOR(EXTRACT(EPOCH FROM CURRENT_TIMESTAMP))",),
            absent=("UNIX_TIMESTAMP",),
        )

    def test_procedural_assignment_translates(self) -> None:
        # Same mechanism, procedural pipeline (dual-pipeline symmetry rule):
        # a SET assignment's RHS scalar expression routes through the same
        # IR ``_emit_function`` as standalone DML.
        out = _ir("mysql", "postgresql", "v_x = UNIX_TIMESTAMP(v_y)")
        assert out is not None, out
        assert "EXTRACT(EPOCH FROM v_y)" in out, out
        assert "UNIX_TIMESTAMP" not in out.upper(), out

    def test_reverse_epoch_extract_maps_to_mysql_timestampdiff(self) -> None:
        # The reverse direction (PG epoch-extract -> MySQL) already existed
        # before this brief: TIMESTAMPDIFF(SECOND, epoch, x) rather than
        # UNIX_TIMESTAMP(x), deliberately — UNIX_TIMESTAMP applies MySQL's
        # SESSION time zone to its argument, which would shift the value
        # relative to PG's tz-naive EXTRACT(EPOCH FROM ...); TIMESTAMPDIFF is
        # a literal difference with no such conversion. Locked in here as a
        # regression guard for the "map the reverse direction" requirement.
        out = _t("SELECT EXTRACT(EPOCH FROM a) FROM t", "mysql", source="postgresql")
        assert_translated(
            out,
            "mysql",
            present=("TIMESTAMPDIFF(SECOND, '1970-01-01 00:00:00', a)",),
            absent=("UNIX_TIMESTAMP", "EXTRACT"),
        )


class TestOracleHashFunctionsToPostgresql:
    """B36b: Oracle RAWTOHEX(x) and STANDARD_HASH(x[, 'ALG']) were untranslated
    built-in leaks (UNIQUE-1151) into PostgreSQL. Live-verified against Oracle
    23 / PostgreSQL 16 for 'abc': MD5/SHA256/SHA384/SHA512 match byte-for-byte
    through PostgreSQL's core md5()/sha256()/sha384()/sha512() (PG 11+, no
    pgcrypto needed), both as raw digest bytes (bare STANDARD_HASH) and as the
    uppercase hex string (RAWTOHEX(STANDARD_HASH(...))). SHA1 — Oracle's own
    default algorithm — has no core-PostgreSQL equivalent and degrades
    honestly (UNIQUE-1235) rather than emit a different digest.
    """

    def test_bare_rawtohex_translates(self) -> None:
        out = _t("SELECT RAWTOHEX('AB') FROM DUAL", "postgresql", source="oracle")
        assert_translated(
            out,
            "postgresql",
            present=("UPPER(ENCODE(CONVERT_TO('AB', 'UTF8'), 'hex'))",),
            absent=("RAWTOHEX",),
        )

    # A CREATE TABLE preamble declares ``x`` as a known character column
    # (the follow-up review found a bare column with no such declaration is
    # NOT a safe default to assume "character" — see
    # TestOracleHashArgumentTypeAwareness — so these tests give it one,
    # keeping their original purpose: pin the hash SQL shape).
    _T_X_VARCHAR2 = "CREATE TABLE t (x VARCHAR2(50));\n"

    def test_rawtohex_standard_hash_sha256_translates(self) -> None:
        out = _t(
            self._T_X_VARCHAR2 + "SELECT RAWTOHEX(STANDARD_HASH(x, 'SHA256')) FROM t",
            "postgresql",
            source="oracle",
        )
        assert_translated(
            out,
            "postgresql",
            present=("UPPER(ENCODE(SHA256(CONVERT_TO(x, 'UTF8')), 'hex'))",),
            absent=("RAWTOHEX", "STANDARD_HASH"),
        )

    def test_rawtohex_standard_hash_md5_translates(self) -> None:
        # MD5 needs a different wrapper: PG's md5() already returns hex TEXT
        # (not bytea like sha256/384/512), so UPPER(...) alone renders the
        # RAWTOHEX-equivalent string — no ENCODE(...,'hex') needed.
        out = _t(
            self._T_X_VARCHAR2 + "SELECT RAWTOHEX(STANDARD_HASH(x, 'MD5')) FROM t",
            "postgresql",
            source="oracle",
        )
        assert_translated(
            out,
            "postgresql",
            present=("UPPER(MD5(CONVERT_TO(x, 'UTF8')))",),
            absent=("RAWTOHEX", "STANDARD_HASH"),
        )

    @pytest.mark.parametrize("alg", ["SHA256", "SHA384", "SHA512"])
    def test_bare_standard_hash_translates(self, alg: str) -> None:
        out = _t(
            self._T_X_VARCHAR2 + f"SELECT STANDARD_HASH(x, '{alg}') FROM t",
            "postgresql",
            source="oracle",
        )
        assert_translated(
            out,
            "postgresql",
            present=(f"{alg}(CONVERT_TO(x, 'UTF8'))",),
            absent=("STANDARD_HASH",),
        )

    def test_bare_standard_hash_md5_translates(self) -> None:
        # Bare STANDARD_HASH returns Oracle RAW bytes; PG's md5() returns hex
        # TEXT, so DECODE(...,'hex') turns it back into the matching bytea
        # value (the byte-for-byte match, live-verified).
        out = _t(
            self._T_X_VARCHAR2 + "SELECT STANDARD_HASH(x, 'MD5') FROM t",
            "postgresql",
            source="oracle",
        )
        assert_translated(
            out,
            "postgresql",
            present=("DECODE(MD5(CONVERT_TO(x, 'UTF8')), 'hex')",),
            absent=("STANDARD_HASH",),
        )

    def test_standard_hash_sha1_degrades_honestly(self) -> None:
        # SHA1 is Oracle's own default algorithm (no ALG argument) and has no
        # core-PostgreSQL equivalent (needs the pgcrypto extension) — must
        # degrade with a warning, never fake a different digest.
        result = Transpiler().transpile(
            "SELECT STANDARD_HASH(x) FROM t", "oracle", "postgresql"
        )
        assert any(w.code == "UNIQUE-1235" for w in result.warnings), result.warnings
        # The carrier note itself names the construct (that's the point of a
        # truthful warning) — check the executable SQL, comments stripped.
        assert "STANDARD_HASH" not in executable_body(result.sql).upper()

    def test_rawtohex_standard_hash_sha1_degrades_honestly(self) -> None:
        result = Transpiler().transpile(
            "SELECT RAWTOHEX(STANDARD_HASH(x, 'SHA1')) FROM t", "oracle", "postgresql"
        )
        assert any(w.code == "UNIQUE-1235" for w in result.warnings), result.warnings
        body = executable_body(result.sql).upper()
        assert "RAWTOHEX" not in body and "STANDARD_HASH" not in body

    def test_procedural_function_body_translates(self) -> None:
        # Same mechanism, procedural pipeline (dual-pipeline symmetry rule) —
        # the exact shape func4 uses in the procedures fixture (a SELECT ...
        # INTO whose expression is RAWTOHEX(STANDARD_HASH(...)) over a
        # concatenation of two parameters — not a bare column, so it is the
        # "default to character" case, not the RAW-column one).
        sql = (
            "CREATE OR REPLACE FUNCTION f4 (payload IN NVARCHAR2, secret IN "
            "NVARCHAR2) RETURN NVARCHAR2 AS\n"
            "    v_ret NVARCHAR2(2000);\n"
            "BEGIN\n"
            "    SELECT RAWTOHEX(STANDARD_HASH(payload || secret, 'SHA256')) "
            "INTO v_ret FROM DUAL;\n"
            "    RETURN v_ret;\n"
            "END;\n/\n"
        )
        out = Transpiler().transpile(sql, "oracle", "postgresql").sql
        assert (
            "UPPER(ENCODE(SHA256(CONVERT_TO(payload || secret, 'UTF8')), 'hex'))" in out
        ), out
        assert "RAWTOHEX" not in out.upper() and "STANDARD_HASH" not in out.upper()


class TestOracleHashArgumentTypeAwareness:
    """B36b follow-up (architect review): a bare RAW-typed column shipped
    ``CONVERT_TO(bytea, 'UTF8')`` with zero warnings — a PostgreSQL runtime
    error ("function convert_to(bytea, ...) does not exist"), not merely a
    wrong value. The argument's SOURCE type must be classified: a RAW/BLOB
    column (harvested from the script's own CREATE TABLE) is already bytea
    on PG, so it is emitted directly with no CONVERT_TO wrapper; a character
    column keeps the CONVERT_TO form; a genuinely unresolvable reference
    declines the whole mapping (the pre-existing untranslated-builtin gate
    degrades the statement honestly, never guessing).
    """

    def test_raw_column_skips_convert_to(self) -> None:
        # The architect's exact regression probe.
        out = _t(
            "CREATE TABLE t2 (b RAW(16));\nSELECT RAWTOHEX(b) FROM t2;",
            "postgresql",
            source="oracle",
        )
        assert_translated(
            out,
            "postgresql",
            present=("UPPER(ENCODE(b, 'hex'))",),
            absent=("RAWTOHEX", "CONVERT_TO"),
        )

    def test_character_column_keeps_convert_to(self) -> None:
        out = _t(
            "CREATE TABLE t3 (x VARCHAR2(30));\nSELECT RAWTOHEX(x) FROM t3;",
            "postgresql",
            source="oracle",
        )
        assert_translated(
            out,
            "postgresql",
            present=("UPPER(ENCODE(CONVERT_TO(x, 'UTF8'), 'hex'))",),
            absent=("RAWTOHEX",),
        )

    def test_raw_column_skips_convert_to_under_standard_hash(self) -> None:
        # The same RAW-vs-character classification applies to STANDARD_HASH's
        # own argument, bare and wrapped in RAWTOHEX — STANDARD_HASH also
        # accepts a RAW value directly (hashing already-binary data).
        out = _t(
            "CREATE TABLE t2 (b RAW(16));\n"
            "SELECT RAWTOHEX(STANDARD_HASH(b, 'SHA256')) FROM t2;",
            "postgresql",
            source="oracle",
        )
        assert_translated(
            out,
            "postgresql",
            present=("UPPER(ENCODE(SHA256(b), 'hex'))",),
            absent=("RAWTOHEX", "STANDARD_HASH", "CONVERT_TO"),
        )
        out2 = _t(
            "CREATE TABLE t2 (b RAW(16));\nSELECT STANDARD_HASH(b, 'MD5') FROM t2;",
            "postgresql",
            source="oracle",
        )
        assert_translated(
            out2,
            "postgresql",
            present=("DECODE(MD5(b), 'hex')",),
            absent=("STANDARD_HASH", "CONVERT_TO"),
        )

    def test_unresolvable_column_declines_to_the_gate(self) -> None:
        # No CREATE TABLE for the queried table anywhere in the script: the
        # argument's type genuinely cannot be determined, so the mapping must
        # NOT guess (CONVERT_TO would break a real RAW column exactly like
        # the regression; ENCODE alone would break a real character column).
        # The pre-existing untranslated-builtin validity gate takes over —
        # an honest whole-statement degrade, not a silent runtime error.
        result = Transpiler().transpile(
            "SELECT RAWTOHEX(unknown_col) FROM some_undeclared_table",
            "oracle",
            "postgresql",
        )
        assert any(w.code == "UNIQUE-1151" for w in result.warnings), result.warnings
        body = executable_body(result.sql).upper()
        assert "CONVERT_TO" not in body and "ENCODE" not in body

    def test_same_named_column_in_unrelated_table_is_not_guessed(self) -> None:
        # t2.b is RAW; t3.b is character. Querying t3 must resolve to t3's
        # OWN type, never borrow t2's just because the bare name matches —
        # a cross-table name collision must not produce a wrong guess either
        # way (RAWTOHEX(x) always needs a decision, so this asserts the
        # correct one: t3 is character, so CONVERT_TO stays).
        out = _t(
            "CREATE TABLE t2 (b RAW(16));\n"
            "CREATE TABLE t3 (b VARCHAR2(30));\n"
            "SELECT RAWTOHEX(b) FROM t3;",
            "postgresql",
            source="oracle",
        )
        assert_translated(
            out,
            "postgresql",
            present=("UPPER(ENCODE(CONVERT_TO(b, 'UTF8'), 'hex'))",),
            absent=("RAWTOHEX",),
        )

    def test_procedural_pipeline_raw_variable_still_declines_safely(self) -> None:
        # The procedural pipeline's scalar-expression seam (dual-pipeline
        # symmetry rule): COLUMN_TYPES/CURRENT_SELECT_TABLE are DML-pipeline
        # concepts with no equivalent procedural-variable tracking yet, so a
        # RAW-typed PROCEDURE variable is "unknown" there too — verifies the
        # decline path is safe (no CONVERT_TO(bytea, ...) shipped) even where
        # the positive RAW classification is not yet reachable.
        out = _ir("oracle", "postgresql", "RAWTOHEX(v_raw_var)")
        assert out is None or "CONVERT_TO" not in out.upper()
