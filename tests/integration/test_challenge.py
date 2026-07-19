# Copyright (c) 2026 Jesús Diéguez Fernández
# SPDX-License-Identifier: MIT
# See the LICENSE file in the project root for full license text.

"""Regression guard over the curated ``tests/fixtures/challenge`` corpus.

Each challenge fixture holds anonymized tricky source constructs (one per
``-- CASE:`` entry) that the transpiler once handled wrong. Transpiling each
case to every other engine must not fall back to an *unrecognized-construct*
carrier (``UNIQUE: Unhandled`` / ``could not translate``) — a documented degrade
for an intrinsically unsupported feature is fine, an unhandled construct is not.
Plus per-case assertions that the specific fix holds.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from unique.core.transpiler import Transpiler

_CHALLENGE_DIR = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "challenge"
_SOURCE_BY_FILE = {
    "challenge_sqlserver.sql": "tsql",
    "challenge_oracle.sql": "oracle",
    "challenge_postgresql.sql": "postgresql",
    "challenge_mysql.sql": "mysql",
}
_ALL_ENGINES = ("tsql", "oracle", "postgresql", "mysql")
_UNRECOGNIZED_MARKERS = ("UNIQUE: Unhandled", "could not translate")


def _read(fname: str) -> str:
    return (_CHALLENGE_DIR / fname).read_text(encoding="utf-8")


def _exec_lines(sql: str) -> str:
    return "\n".join(ln for ln in sql.splitlines() if not ln.lstrip().startswith("--"))


# A case is tagged ``-- CASE[fixed]:`` (BLUE faithfully corrected it — strictly
# guarded), ``-- CASE[open]:`` (RED found it, not yet fixed — backlog, only
# smoke-checked), or ``-- CASE[limit]:`` (a genuine no-statement-level-
# compensation divergence the human APPROVED as a documented limit — e.g.
# collation case/accent sensitivity, LENGTH bytes-vs-chars: it produces valid
# output with a different value, so it is neither a defect nor a faithful fix;
# it must cite docs/03-unsupported.md). An untagged ``-- CASE:`` is treated as
# fixed. "Corpus done" means zero ``[open]``.
_CASE_HEAD = r"-- CASE(?:\[(?:open|fixed|limit)\])?:"


def _cases(fname: str) -> list[str]:
    """Split a fixture into its ``-- CASE:`` blocks (each self-contained)."""
    blocks = re.split(rf"(?m)^(?={_CASE_HEAD})", _read(fname))
    return [b.strip() for b in blocks if re.match(_CASE_HEAD, b.strip())]


def _status(block: str) -> str:
    m = re.match(r"-- CASE\[(open|fixed|limit)\]:", block.strip())
    return m.group(1) if m else "fixed"


def _case(fname: str, keyword: str) -> str:
    for block in _cases(fname):
        if keyword.lower() in block.splitlines()[0].lower():
            return block
    raise KeyError(f"no CASE matching {keyword!r} in {fname}")


def _tx(sql: str, source: str, target: str) -> str:
    return Transpiler().transpile(sql, source=source, target=target).sql


def _cases_by_status(want: str) -> list[tuple[str, str, int]]:
    out: list[tuple[str, str, int]] = []
    for fname, src in _SOURCE_BY_FILE.items():
        for i, block in enumerate(_cases(fname)):
            if _status(block) == want:
                out.append((fname, src, i))
    return out


def test_fixed_cases_have_no_unrecognized_construct() -> None:
    """A closed case must transpile to every engine without an unrecognized
    carrier (a documented degrade is fine, an Unhandled construct is not).

    Kept as ONE looping test (not parametrized per case): these generic guards
    check *absence* of a marker, so they pass under an identity transpiler and
    would otherwise dilute the identity-mutation gate as the corpus grows. The
    real assertion-quality lives in the specific ``[fixed]`` classes below."""
    failures: list[str] = []
    for fname, source, i in _cases_by_status("fixed"):
        sql = _cases(fname)[i]
        for target in _ALL_ENGINES:
            if target == source:
                continue
            out = _tx(sql, source, target)
            for marker in _UNRECOGNIZED_MARKERS:
                if marker in out:
                    failures.append(f"{fname}[{i}] -> {target}: {marker!r}")
    assert not failures, "unrecognized carrier on fixed cases:\n" + "\n".join(
        failures[:20]
    )


def test_open_cases_transpile_without_crashing() -> None:
    """OPEN (RED-found, unfixed) cases are the known-defect backlog — output is
    wrong on some target. We only assert the transpiler does not *crash*;
    correctness is BLUE's job (flip to ``[fixed]`` with a real assertion). ONE
    looping test on purpose (a no-crash smoke check passes under identity, so
    parametrizing it per case would swamp the identity-mutation gate). See
    tests/fixtures/challenge/FINDINGS.md."""
    for fname, source, i in _cases_by_status("open"):
        sql = _cases(fname)[i]
        for target in _ALL_ENGINES:
            if target == source:
                continue
            _tx(sql, source, target)  # must not raise


def test_limit_cases_warn_and_annotate_on_every_failing_target() -> None:
    """A ``[limit]`` case is a human-APPROVED divergence with no statement-level
    compensation (collation, LENGTH bytes-vs-chars). It must NEVER ship silently:
    on each target where the value diverges the transpiler must (1) emit a
    ``validity_gate``/warning AND (2) annotate the output with a ``UNIQUE:``
    comment naming the divergence, while keeping the SQL valid (no unrecognized
    carrier). The case comment must also cite ``03-unsupported`` for traceability.

    The divergent targets are read from the case's ``fails on <engines>`` note.
    """
    failures: list[str] = []
    for fname, source, i in _cases_by_status("limit"):
        block = _cases(fname)[i]
        head = block.splitlines()[0]
        if "03-unsupported" not in head.lower():
            failures.append(f"{fname}[{i}]: [limit] case must cite 03-unsupported")
        m = re.search(r"fails on ([^.—]+)", head)
        diverging = (
            {t.strip() for t in m.group(1).replace("sqlserver", "tsql").split(",")}
            if m
            else set()
        )
        for target in _ALL_ENGINES:
            if target == source or target not in diverging:
                continue
            result = Transpiler().transpile(block, source=source, target=target)
            if not result.warnings:
                failures.append(f"{fname}[{i}] -> {target}: no warning for a limit")
            if "UNIQUE:" not in result.sql:
                failures.append(f"{fname}[{i}] -> {target}: no UNIQUE annotation")
            for marker in _UNRECOGNIZED_MARKERS:
                if marker in result.sql:
                    failures.append(f"{fname}[{i}] -> {target}: {marker!r}")
    assert not failures, "\n".join(failures[:20])


class TestOracleSelfQualifiedParam:
    """``get_top_rows.row_limit`` (Oracle self-qualified parameter) resolves to
    the target variable and never leaks the ``<routine>.`` qualifier."""

    def _out(self, target: str) -> str:
        return _tx(_case("challenge_oracle.sql", "self-qualified"), "oracle", target)

    def test_tsql_resolves_to_at_variable(self) -> None:
        out = self._out("tsql")
        assert "SELECT TOP (@row_limit)" in out, out
        assert "get_top_rows." not in _exec_lines(out), out

    def test_mysql_resolves_to_bare_param(self) -> None:
        out = self._out("mysql")
        body = _exec_lines(out)
        assert "get_top_rows." not in body, out
        assert "LIMIT row_limit" in body, out


class TestTsqlCreateProcAbbreviation:
    """``CREATE PROC`` transpiles like ``CREATE PROCEDURE`` and never leaks the
    T-SQL-only ``PROC`` keyword to another engine."""

    @pytest.mark.parametrize("target", ("postgresql", "oracle", "mysql"))
    def test_proc_becomes_procedure(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "PROC abbreviation"), "tsql", target)
        assert "PROCEDURE" in out.upper(), out
        assert not re.search(
            r"\bPROC\b(?!EDURE)", _exec_lines(out), re.IGNORECASE
        ), f"leaked PROC abbreviation ({target}):\n{out}"


class TestTsqlCreateOrAlter:
    """``CREATE OR ALTER`` (T-SQL 2016+) routes to the procedural engine and maps
    to the other engines' ``CREATE OR REPLACE`` — never an Unhandled carrier."""

    @pytest.mark.parametrize("target", ("postgresql", "oracle"))
    def test_maps_to_create_or_replace(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "CREATE OR ALTER"), "tsql", target)
        assert "CREATE OR REPLACE PROCEDURE" in out, out
        assert "UNIQUE: Unhandled" not in out, out

    def test_tsql_roundtrip_preserves_or_alter(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "CREATE OR ALTER"), "tsql", "tsql")
        assert "CREATE OR ALTER PROCEDURE" in out, out


class TestTrimCharacterSet:
    """``TRIM([BOTH|LEADING|TRAILING] chars FROM string)`` keeps its operands in
    order (a swap silently trimmed the wrong argument on every target) and, into
    Oracle, uses LTRIM/RTRIM so a multi-character set never hits ORA-30001."""

    def test_tsql_both_into_oracle_uses_ltrim_rtrim(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-trim-chars"), "tsql", "oracle")
        # set 'x' stripped from 'xxabcxx' — operands must not be swapped, and
        # Oracle must not receive TRIM(BOTH set FROM s) (ORA-30001 on >1 char).
        assert "LTRIM(RTRIM('xxabcxx', 'x'), 'x')" in out, out
        assert "TRIM(BOTH" not in out, out

    @pytest.mark.parametrize("target", ("postgresql", "mysql"))
    def test_tsql_both_keeps_operand_order(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-trim-chars"), "tsql", target)
        # 'x' is the trim set, 'xxabcxx' the string — the string follows FROM.
        assert "TRIM(BOTH 'x' FROM 'xxabcxx')" in out, out

    def test_mysql_leading_into_oracle_uses_ltrim(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-trim-leading"), "mysql", "oracle")
        assert "LTRIM('007', '0')" in _exec_lines(out), out


class TestDateLiteralIntoOracle:
    """Date built-ins over ISO string literals emit the ANSI ``DATE '…'`` literal
    for Oracle/PG date math — Oracle can't implicitly convert an ISO string to a
    DATE (NLS_DATE_FORMAT, ORA-01861), and a bare CAST(str AS DATE) inherits it."""

    def test_datediff_into_oracle_uses_ansi_date_literal(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-datediff "), "tsql", "oracle")
        assert "DATE '2020-01-10'" in out and "DATE '2020-01-01'" in out, out
        # the raw string must not be handed to CAST(... AS DATE) unwrapped.
        assert "CAST('2020-01-10'" not in out, out

    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_datediff_big_faithful(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-datediff-big"), "tsql", target)
        assert re.search(r"DATE '\d{4}-\d\d-\d\d'", out), out


class TestStringAggTextCastIntoPg:
    """PG ``string_agg`` will not implicitly stringify its value (unlike T-SQL
    STRING_AGG / Oracle LISTAGG); an integer value is cast to text so PG doesn't
    reject ``string_agg(integer, unknown)``, and the WITHIN GROUP order folds
    into the aggregate call."""

    def test_tsql_within_group_into_pg_casts_value(self) -> None:
        out = _tx(
            _case("challenge_sqlserver.sql", "ts-stragg-within"), "tsql", "postgresql"
        )
        assert "STRING_AGG(CAST(x AS TEXT), ',' ORDER BY x)" in out, out

    def test_oracle_listagg_into_pg_casts_value(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-listagg "), "oracle", "postgresql")
        assert "STRING_AGG(CAST(x AS TEXT), ',' ORDER BY x)" in out, out


class TestDdlConstraintClausesSurvive:
    """Inline CHECK and FK REFERENCES/ON DELETE constraints survive to every
    target (they were once silently dropped; the RC-3 constraint path keeps
    them). Guarded so a regression to the silent-drop is caught."""

    @pytest.mark.parametrize("target", ("mysql", "oracle", "tsql"))
    def test_inline_check_survives(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "postgresql-drop-CHECK"),
            "postgresql",
            target,
        )
        assert re.search(r"(?i)CHECK\s*\(", _exec_lines(out)), out

    @pytest.mark.parametrize("target", ("mysql", "oracle", "tsql"))
    def test_fk_references_survives(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "postgresql-drop5-REFERENCES"),
            "postgresql",
            target,
        )
        assert re.search(r"(?i)REFERENCES\b", _exec_lines(out)), out


class TestNegativeSubstr:
    """Oracle/MySQL SUBSTR(s, -n, len) counts from the END; PG/T-SQL SUBSTRING is
    1-indexed and reads -n literally. The start is rewritten to LENGTH(s)-n+1."""

    @pytest.mark.parametrize("target", ("postgresql", "tsql"))
    def test_negative_start_uses_length_offset(self, target: str) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-substr-neg"), "oracle", target)
        assert re.search(
            r"(?i)(LEN|LENGTH)\('abcdef'\)\s*\+\s*\(-3\)\s*\+\s*1", out
        ), out


class TestConcatNumberIntoTsql:
    """Oracle/PG ``||`` (and MySQL CONCAT) stringify numeric operands; T-SQL
    ``+`` would do arithmetic (2||3 → 5) or error (string+number). A concat with
    a numeric operand emits T-SQL CONCAT()."""

    def test_number_concat_uses_concat(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-num-concat"), "oracle", "tsql")
        assert "CONCAT(2, 3)" in out and "2 + 3" not in out, out

    def test_string_number_concat_uses_concat(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-concat-num"), "oracle", "tsql")
        assert "CONCAT('a', 5)" in out, out


class TestLikeBackslashEscape:
    """PG/MySQL LIKE use backslash as the default escape char; Oracle/T-SQL have
    none. A backslash pattern gets an explicit ``ESCAPE '\\'`` so the literal
    wildcard match is preserved."""

    @pytest.mark.parametrize("target", ("oracle", "tsql"))
    def test_backslash_pattern_gets_escape(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-like-escape"), "mysql", target)
        assert "ESCAPE '\\'" in out, out


class TestSetOperationAll:
    """INTERSECT ALL / EXCEPT ALL keep duplicates — the ALL was dropped (the row
    multiset silently changed). MySQL (8.0.31+) and PG preserve it; Oracle/T-SQL
    (no ALL form) fall back to the distinct spelling."""

    def test_except_all_preserved_into_mysql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-except-all"), "postgresql", "mysql"
        )
        assert "EXCEPT ALL" in out, out

    def test_intersect_all_preserved_into_mysql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-intersect-all"), "postgresql", "mysql"
        )
        assert "INTERSECT ALL" in out, out


class TestMoneyCastType:
    """T-SQL MONEY/SMALLMONEY are fixed-scale decimals — mapped in a CAST target
    too (not only as a column type): NUMBER(19,4)/(10,4) on Oracle, NUMERIC on
    PG, DECIMAL on MySQL."""

    def test_money_arith_cast_into_oracle_pg(self) -> None:
        src = _case("challenge_sqlserver.sql", "ts-money-arith")
        assert "CAST(10.5 AS NUMBER(19,4))" in _tx(src, "tsql", "oracle")
        assert "NUMERIC(19,4)" in _tx(src, "tsql", "postgresql")
        assert "AS MONEY" not in _tx(src, "tsql", "oracle").upper()


class TestInitcapSingleArg:
    """PG/Oracle INITCAP take one argument; sqlglot's appended delimiter set
    (a 2-arg Snowflake form) is dropped. T-SQL/MySQL have none → degrade."""

    def test_initcap_into_oracle_single_arg(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-initcap"), "postgresql", "oracle"
        )
        assert "INITCAP('hello world')" in out, out

    def test_initcap_into_tsql_degrades(self) -> None:
        r = Transpiler().transpile(
            _case("challenge_postgresql.sql", "pg-initcap"), "postgresql", "tsql"
        )
        assert "-- UNIQUE:" in r.sql and r.warnings, r.sql


class TestDatetimeFromParts:
    """T-SQL ``DATETIMEFROMPARTS(y,mo,d,h,mi,s,ms)`` constructs a timestamp:
    PG make_timestamp, Oracle TO_TIMESTAMP + interval, MySQL TIMESTAMP + interval
    — no leaked TIMESTAMP_FROM_PARTS."""

    def test_datetimefromparts_per_engine(self) -> None:
        src = _case("challenge_sqlserver.sql", "ts-datetimefromparts")
        assert "make_timestamp(" in _tx(src, "tsql", "postgresql")
        oracle = _tx(src, "tsql", "oracle")
        assert "TO_TIMESTAMP(" in oracle and "NUMTODSINTERVAL(" in oracle
        assert "TIMESTAMP(CONCAT(" in _tx(src, "tsql", "mysql")
        for tgt in ("postgresql", "oracle", "mysql"):
            assert "_FROM_PARTS" not in _exec_lines(_tx(src, "tsql", tgt)).upper()


class TestSequenceNextValue:
    """T-SQL ``NEXT VALUE FOR seq`` maps to Oracle ``seq.NEXTVAL`` and PG
    ``nextval('seq')``; MySQL (no sequences) degrades with a warning."""

    def test_next_value_for_into_oracle_and_pg(self) -> None:
        src = _case("challenge_sqlserver.sql", "ts-sequence-next")
        assert "seq.NEXTVAL" in _tx(src, "tsql", "oracle")
        assert "nextval('seq')" in _tx(src, "tsql", "postgresql")

    def test_next_value_for_mysql_degrades(self) -> None:
        r = Transpiler().transpile(
            _case("challenge_sqlserver.sql", "ts-seq-use"), "tsql", "mysql"
        )
        assert "-- UNIQUE:" in r.sql and r.warnings, r.sql


class TestNcharCharCodePoint:
    """T-SQL ``CHAR(n)``/``NCHAR(n)`` (code point → character) map to each
    engine's spelling: Oracle CHR/NCHR, PG CHR, MySQL CHAR(... USING cs) — and
    MySQL needs a charset so the result is a character, not a BINARY string."""

    def test_char_nchar_into_each_engine(self) -> None:
        src = _case("challenge_sqlserver.sql", "ts-ascii-char")
        assert "NCHR(65)" in _tx(src, "tsql", "oracle"), _tx(src, "tsql", "oracle")
        my = _tx(src, "tsql", "mysql")
        assert "CHAR(65 USING latin1)" in my and "CHAR(65 USING utf16)" in my, my
        assert "NCHAR(" not in _exec_lines(my), my  # no leaked NCHAR


class TestTsqlBeginTransaction:
    """``BEGIN TRANSACTION`` maps to each engine's transaction-open form; Oracle
    (implicit transactions) drops it with a documented carrier + warning."""

    def _case_sql(self) -> str:
        return _case("challenge_sqlserver.sql", "BEGIN TRANSACTION")

    def test_tsql_keeps_begin_transaction(self) -> None:
        assert "BEGIN TRANSACTION" in _tx(self._case_sql(), "tsql", "tsql")

    @pytest.mark.parametrize("target", ("postgresql", "mysql"))
    def test_other_engines_open_a_transaction(self, target: str) -> None:
        body = _exec_lines(_tx(self._case_sql(), "tsql", target))
        assert re.search(r"(?i)\bBEGIN\b|\bSTART TRANSACTION\b", body), body

    def test_oracle_drops_with_warning(self) -> None:
        result = Transpiler().transpile(
            self._case_sql(), source="tsql", target="oracle"
        )
        assert "BEGIN" not in _exec_lines(result.sql), result.sql
        assert any("BEGIN TRANSACTION dropped" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestLpadShrink:
    """LPAD whose target length is shorter than the string truncates it to the
    LEFT n chars (LPAD('hello', 3) = 'hel'); the T-SQL LEFT(REPLICATE(...)) form
    pads nothing (CASE ... ELSE 0) and keeps only LEFT(s, n) (live-verified)."""

    def test_pg_lpad_shrink_keeps_left_chars(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-lpad-shrink"), "postgresql", "tsql"
        )
        assert "ELSE 0 END) + LEFT('hello', 3)" in out, out

    def test_mysql_lpad_trunc_keeps_left_chars(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-lpad-trunc"), "mysql", "tsql")
        assert "ELSE 0 END) + LEFT('abc', 2)" in out, out


class TestLogBase10:
    """A 1-arg LOG in the IR only ever comes from PostgreSQL, whose LOG(x) is
    base-10 (MySQL/T-SQL LOG(x) is the natural log → LN; Oracle's LOG needs two
    args). The base-10 sense must be named explicitly, and T-SQL's native LOG10
    is used for the two-arg base-10 case to avoid LOG(x, 10)'s float drift."""

    def test_pg_single_arg_log_is_base_10(self) -> None:
        assert "LOG10(100)" in _tx(
            _case("challenge_postgresql.sql", "pg-log-base"), "postgresql", "tsql"
        )
        assert "LOG10(100)" in _tx(
            _case("challenge_postgresql.sql", "pg-log-base"), "postgresql", "mysql"
        )
        assert "LOG(10, 100)" in _tx(
            _case("challenge_postgresql.sql", "pg-log-base"), "postgresql", "oracle"
        )

    def test_tsql_base_10_uses_native_log10(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-log2-log10"), "mysql", "tsql")
        assert "LOG10(1000)" in out, out
        assert "LOG(8, 2)" in out, out  # LOG2 keeps the general arg-swapped form


class TestWindowFramePreserved:
    """A window frame (ROWS/RANGE BETWEEN …) is standard SQL on every engine, but
    the IR dropped it — silently turning a running total into a grand total. It is
    now captured and emitted verbatim (live-verified: PG's [1, 3] running sum is
    reproduced on T-SQL, Oracle and MySQL)."""

    @pytest.mark.parametrize("target", ("tsql", "oracle", "mysql"))
    def test_rows_frame_survives(self, target: str) -> None:
        out = _tx(_case("challenge_postgresql.sql", "qdrop-ROWS"), "postgresql", target)
        assert "ROWS BETWEEN 1 PRECEDING AND CURRENT ROW" in out, out


class TestGroupByRollup:
    """GROUP BY ROLLUP was dropped by the IR — MySQL's ``x WITH ROLLUP`` lost the
    subtotal rows and, worse, the standard ``ROLLUP(x)`` spelling lost the entire
    GROUP BY. MySQL trails ``WITH ROLLUP``; every other engine wraps the columns.
    Live-verified: the super-aggregate (NULL) rows are reproduced on all engines
    (multiset compare — the cases carry no ORDER BY)."""

    @pytest.mark.parametrize("target", ("tsql", "oracle", "postgresql"))
    def test_mysql_with_rollup_becomes_standard_rollup(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "qdrop-ROLLUP"), "mysql", target)
        assert "GROUP BY ROLLUP(x)" in out, out

    @pytest.mark.parametrize("target", ("tsql", "oracle"))
    def test_pg_rollup_survives_as_standard(self, target: str) -> None:
        out = _tx(_case("challenge_postgresql.sql", "pg-rollup2"), "postgresql", target)
        assert "GROUP BY ROLLUP(a, b)" in out, out

    def test_pg_rollup_to_mysql_uses_with_rollup(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-rollup2"), "postgresql", "mysql"
        )
        assert "GROUP BY a, b WITH ROLLUP" in out, out

    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_cube_survives_natively(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-cube"), "tsql", target)
        assert "GROUP BY CUBE(a, b)" in out, out

    def test_cube_to_mysql_degrades_with_carrier(self) -> None:
        # MySQL has no CUBE: keep the base grouping, but never silently — a
        # carrier + warning must document the omitted super-aggregate rows.
        result = Transpiler().transpile(
            _case("challenge_sqlserver.sql", "ts-cube"), "tsql", "mysql"
        )
        assert "CUBE" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE: MySQL has no GROUP BY CUBE" in result.sql, result.sql
        assert any("CUBE" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]

    @pytest.mark.parametrize("target", ("oracle", "tsql"))
    def test_grouping_sets_survives_natively(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-grouping-sets"), "postgresql", target
        )
        assert "GROUP BY GROUPING SETS ((x), ())" in out, out

    def test_grouping_sets_to_mysql_degrades_with_carrier(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_oracle.sql", "ora-grouping-sets"), "oracle", "mysql"
        )
        assert "GROUPING SETS" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE: MySQL has no GROUP BY GROUPING SETS" in result.sql, result.sql
        assert any("GROUPING SETS" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestForUpdateLockCarrier:
    """PostgreSQL's FOR UPDATE row lock has no trailing-clause form on T-SQL
    (sqlglot drops it silently); Oracle/MySQL keep it. On T-SQL the loss is now
    surfaced as a documented carrier + warning, and the SQL stays valid."""

    def test_tsql_surfaces_a_warning_and_carrier(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", "qdrop-FOR"), "postgresql", "tsql"
        )
        assert "FOR UPDATE" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE: T-SQL has no FOR UPDATE" in result.sql, result.sql
        assert any("FOR UPDATE" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]

    @pytest.mark.parametrize("target", ("oracle", "mysql"))
    def test_oracle_mysql_keep_the_lock(self, target: str) -> None:
        out = _tx(_case("challenge_postgresql.sql", "qdrop-FOR"), "postgresql", target)
        assert "FOR UPDATE" in out.upper(), out
        assert "UNIQUE:" not in out, out


class TestAlterNotValidStripped:
    """PostgreSQL's ADD CONSTRAINT … NOT VALID (defer validating existing rows)
    has no equivalent elsewhere and passed through as a syntax error. It is now
    stripped — the constraint definition is identical — leaving valid SQL, with a
    carrier + warning documenting the target's immediate validation."""

    @pytest.mark.parametrize("keyword", ("pg-alter-notvalid", "pg-check-notvalid"))
    @pytest.mark.parametrize("target", ("tsql", "oracle", "mysql"))
    def test_not_valid_is_stripped_with_carrier(
        self, keyword: str, target: str
    ) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", keyword), "postgresql", target
        )
        assert "NOT VALID" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE:" in result.sql and "NOT VALID" in result.sql, result.sql
        assert any("NOT VALID" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestGeneratedColumn:
    """``GENERATED ALWAYS AS (expr)`` is a COMPUTED column, but sqlglot models it
    with the identity node — it was corrupted into ``IDENTITY(1,1)`` (an
    auto-increment). It now emits each engine's computed-column form: T-SQL
    ``b AS (expr)`` (no declared type), PG ``… GENERATED ALWAYS AS (expr) STORED``,
    Oracle/MySQL the VIRTUAL form. Live-verified: a=5 yields b=6 on all three."""

    _GEN = "CREATE TABLE t (a INT, b INT GENERATED ALWAYS AS (a + 1))"

    def test_generated_always_is_computed_not_identity(self) -> None:
        out = _tx(self._GEN, "mysql", "tsql")
        assert "b AS (a + 1)" in out, out
        assert "IDENTITY" not in out.upper(), out

    def test_pg_uses_stored_generated(self) -> None:
        out = _tx(self._GEN, "mysql", "postgresql")
        assert "GENERATED ALWAYS AS (a + 1) STORED" in out, out

    def test_oracle_keeps_generated_expression(self) -> None:
        out = _tx(self._GEN, "mysql", "oracle")
        assert "GENERATED ALWAYS AS (a + 1)" in out, out
        assert "IDENTITY" not in out.upper(), out

    def test_mysql_shorthand_computed_column_survives_on_tsql(self) -> None:
        # The corpus case uses MySQL's ``AS (expr) STORED`` shorthand (a distinct
        # sqlglot node); its computed column reaches T-SQL as ``AS … PERSISTED``
        # (live-verified valid) rather than being dropped.
        out = _tx(_case("challenge_mysql.sql", "drop-GENERATED"), "mysql", "tsql")
        assert re.search(r"(?i)\bb\s+AS\b.*\ba\s*\+\s*1", _exec_lines(out)), out
        assert "IDENTITY" not in out.upper(), out


class TestCreateIndexConcurrently:
    """PostgreSQL's CREATE INDEX CONCURRENTLY (non-locking build) has no T-SQL or
    MySQL equivalent; the index is identical, so the option is dropped but never
    silently — a carrier + warning documents the target's default locking."""

    @pytest.mark.parametrize("target", ("tsql", "mysql"))
    def test_concurrently_dropped_with_carrier(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", "drop2-CONCURRENTLY"),
            "postgresql",
            target,
        )
        assert "CONCURRENTLY" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE: CONCURRENTLY" in result.sql, result.sql
        assert any("CONCURRENTLY" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestIdentitySeedPreserved:
    """An IDENTITY seed/step (T-SQL ``IDENTITY(100, 5)``, PG/Oracle ``START WITH
    100 INCREMENT BY 5``) must survive so the sequence does not silently restart
    at 1 on the target (RC-3). Live-verified: the first inserted row gets id 100."""

    def test_tsql_seed_into_pg(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "drop2-100"), "tsql", "postgresql")
        assert "START WITH 100 INCREMENT BY 5" in out, out

    def test_oracle_seed_into_tsql(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "drop2-100"), "oracle", "tsql")
        assert "IDENTITY(100," in out, out

    @pytest.mark.parametrize("target", ("oracle", "tsql"))
    def test_pg_seed_and_step_survive(self, target: str) -> None:
        out = _tx(_case("challenge_postgresql.sql", "drop2-100"), "postgresql", target)
        assert "100" in _exec_lines(out) and (
            "START WITH 100 INCREMENT BY 5" in out or "IDENTITY(100,5)" in out
        ), out


class TestCheckInConstraintPreserved:
    """A ``CHECK (a IN (…))`` constraint must survive to every engine and keep
    enforcing (live-verified: a value outside the set is rejected)."""

    @pytest.mark.parametrize("target", ("tsql", "mysql", "oracle"))
    def test_check_in_survives(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "drop5-CHECK"), "postgresql", target
        )
        assert "CHECK (a IN (1, 2, 3))" in out, out


class TestExcludeConstraintCarrier:
    """PostgreSQL's EXCLUDE exclusion constraint has no equivalent on any other
    engine; it was dropped silently. It now degrades to a documented carrier +
    warning (the table itself stays valid), never a silent loss."""

    @pytest.mark.parametrize("target", ("tsql", "mysql", "oracle"))
    def test_exclude_degrades_with_carrier(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", "drop2-EXCLUDE"), "postgresql", target
        )
        assert "EXCLUDE" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE: PostgreSQL EXCLUDE" in result.sql, result.sql
        assert any("EXCLUDE" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestOnUpdateTimestampCarrier:
    """MySQL's ``ON UPDATE CURRENT_TIMESTAMP`` auto-update column attribute has no
    column-level equivalent on T-SQL/Oracle/PG (they need a trigger); it was
    dropped silently and now degrades to a documented carrier + warning while the
    table stays valid. MySQL keeps the clause inline."""

    @pytest.mark.parametrize("target", ("tsql", "oracle", "postgresql"))
    def test_on_update_degrades_with_carrier(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_mysql.sql", "drop2-ON"), "mysql", target
        )
        assert "ON UPDATE" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE: MySQL's" in result.sql and "ON UPDATE" in result.sql, result.sql
        assert any("ON UPDATE" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestByDefaultIdentityIntoTsql:
    """PostgreSQL's ``GENERATED BY DEFAULT AS IDENTITY`` maps to T-SQL's native
    ``IDENTITY(1,1)`` (T-SQL has no GENERATED/BY DEFAULT keyword — that spelling
    is the faithful equivalent). Live-verified: the first inserted row gets id 1."""

    def test_identity_survives_into_tsql(self) -> None:
        out = _tx(_case("challenge_postgresql.sql", "drop4-BY"), "postgresql", "tsql")
        assert "IDENTITY(1,1)" in out, out


class TestMemoryOptimizedCarrier:
    """T-SQL's WITH (MEMORY_OPTIMIZED = ON) is a physical In-Memory OLTP storage
    option (no logical/value impact) with no equivalent elsewhere; it was dropped
    silently. Off T-SQL it now degrades to a documented carrier + warning while
    the table stays valid (a regular disk table)."""

    @pytest.mark.parametrize("target", ("postgresql", "mysql", "oracle"))
    def test_memory_optimized_degrades_with_carrier(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_sqlserver.sql", "drop5-MEMORY"), "tsql", target
        )
        assert "MEMORY_OPTIMIZED" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE: T-SQL In-Memory OLTP" in result.sql, result.sql
        assert any("MEMORY_OPTIMIZED" in w.message for w in result.warnings), [
            w.message for w in result.warnings
        ]


class TestCollationCarrier:
    """Collation names are engine-specific (Oracle BINARY_CI, PG "en_US", MySQL
    utf8mb4_…) with no portable mapping; a dropped COLLATE was silent. Off the
    source engine it now degrades to a documented carrier + warning (a live DB
    connection could resolve the actual collation), and the table stays valid."""

    def test_oracle_column_collate_carried(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_oracle.sql", "drop4-COLLATE"), "oracle", "tsql"
        )
        assert "COLLATE" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE:" in result.sql and "collation" in result.sql, result.sql
        assert any("collation" in w.message for w in result.warnings), result.sql

    def test_pg_column_collate_carried(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_postgresql.sql", "drop4-COLLATE"), "postgresql", "mysql"
        )
        assert "UNIQUE:" in result.sql and "collation" in result.sql, result.sql
        assert result.warnings, result.sql

    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_mysql_table_collate_carried(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_mysql.sql", "drop4-COLLATE|utf8"), "mysql", target
        )
        assert "COLLATE" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE:" in result.sql and "collation" in result.sql, result.sql
        assert any("collation" in w.message for w in result.warnings), result.sql


class TestCharacterSetCarrier:
    """MySQL CHARACTER SET / DEFAULT CHARSET (column and table level) is
    engine-specific with no portable mapping; a dropped charset was silent. Off
    MySQL it degrades to a documented carrier + warning while the table stays
    valid (same contract as a dropped COLLATE)."""

    def test_column_character_set_carried(self) -> None:
        result = Transpiler().transpile(
            _case("challenge_mysql.sql", "drop2-latin1"), "mysql", "oracle"
        )
        assert "CHARACTER SET" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE:" in result.sql and "charset" in result.sql, result.sql
        assert result.warnings, result.sql

    @pytest.mark.parametrize("target", ("oracle", "postgresql", "tsql"))
    def test_table_default_charset_carried(self, target: str) -> None:
        result = Transpiler().transpile(
            _case("challenge_mysql.sql", "drop5-utf8mb4"), "mysql", target
        )
        assert "CHARSET" not in _exec_lines(result.sql).upper(), result.sql
        assert "UNIQUE:" in result.sql and "charset" in result.sql, result.sql
        assert result.warnings, result.sql


class TestUnsignedCheck:
    """A MySQL UNSIGNED integer widens to a type that holds its range (INT
    UNSIGNED -> BIGINT), and the non-negativity — which the other engines can't
    put in the type — is preserved with CHECK (col >= 0). Live-verified: the max
    unsigned value stores and a negative is rejected."""

    @pytest.mark.parametrize("target", ("tsql", "oracle", "postgresql"))
    def test_unsigned_adds_nonnegative_check(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "drop4-UNSIGNED"), "mysql", target)
        assert re.search(r"(?i)CHECK\s*\(\s*a\s*>=\s*0\s*\)", out), out

    def test_mysql_keeps_unsigned(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "drop4-UNSIGNED"), "mysql", "mysql")
        assert "UNSIGNED" in out.upper(), out


class TestDateLiteralSubtraction:
    """``DATE 'a' - DATE 'b'`` is a day count: Oracle/PG subtract dates natively,
    T-SQL/MySQL need DATEDIFF. sqlglot's DATE_STR_TO_DATE wrapper unwrapped to a
    bare string, so ``str - str`` computed nothing. Live-verified: 60 days on all
    four engines."""

    def test_tsql_uses_datediff(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "date-diff-days"), "oracle", "tsql")
        assert "DATEDIFF(DAY," in out and "AS DATE)" in out, out

    def test_pg_subtracts_dates(self) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "date-diff-days"), "oracle", "postgresql"
        )
        assert "DATE '2020-03-01' - DATE '2020-01-01'" in out, out

    def test_mysql_uses_datediff(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "date-diff-days"), "oracle", "mysql")
        assert "DATEDIFF(CAST(" in out, out


class TestMysqlModByZero:
    """MySQL's ``x MOD 0`` returns NULL; the other engines error (PG/T-SQL) or
    return the dividend (Oracle). The MySQL->other emit guards the divisor with
    ``CASE WHEN divisor = 0 THEN NULL`` so the value matches. Live-verified:
    ``5 MOD 0 IS NULL`` is 1 on Oracle."""

    @pytest.mark.parametrize("keyword", ("my-mod-zero", "my-mod-edge"))
    @pytest.mark.parametrize("target", ("oracle", "postgresql", "tsql"))
    def test_mod_zero_guarded(self, keyword: str, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", target)
        assert re.search(r"(?i)CASE\s+WHEN\s+0\s*=\s*0\s+THEN\s+NULL", out), out


class TestOracleCastIntRounds:
    """Oracle CAST-to-integer ROUNDS (CAST('3.9' AS INT) = 4); MySQL's
    CAST(... AS SIGNED) truncates a string. The Oracle->MySQL emit rounds first
    so the value matches (live-verified: 4, not 3)."""

    def test_mysql_rounds_the_cast(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "cast-int-edge"), "oracle", "mysql")
        assert "CAST(ROUND('3.9') AS SIGNED)" in out, out


class TestGreatestLeastNullPropagation:
    """MySQL's GREATEST/LEAST return NULL if any argument is NULL; PG and T-SQL
    ignore NULLs. The MySQL->PG/T-SQL emit guards with CASE WHEN <any> IS NULL
    THEN NULL. Live-verified NULL, not 3/1."""

    @pytest.mark.parametrize(
        "keyword,target",
        [
            ("my-greatest-null", "postgresql"),
            ("my-greatest-null", "tsql"),
            ("my-least-null2", "postgresql"),
            ("my-least-null2", "tsql"),
            ("my-greatest-null2", "postgresql"),
            ("my-least-greatest-null", "tsql"),
        ],
    )
    def test_null_propagates(self, keyword: str, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", target)
        assert re.search(r"(?i)CASE\s+WHEN\b.*\bIS\s+NULL\b.*THEN\s+NULL", out), out


class TestNegativeLengthStringFns:
    """MySQL LEFT / REPEAT with a negative count return '' ; PostgreSQL LEFT
    reads it as "all but the last |n|" and T-SQL REPLICATE returns NULL. The
    MySQL-source emit clamps the count to 0. Live-verified empty string."""

    def test_left_negative_clamps(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-left-neg"), "mysql", "postgresql")
        assert re.search(r"(?i)LEFT\(.*CASE\s+WHEN\b.*<\s*0\s+THEN\s+0", out), out

    def test_repeat_negative_clamps(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-repeat-neg"), "mysql", "tsql")
        assert re.search(r"(?i)REPLICATE\(.*CASE\s+WHEN\b.*<\s*0\s+THEN\s+0", out), out

    def test_repeat_float_rounds(self) -> None:
        # MySQL rounds a float count (REPEAT('ab', 2.9) = 'ababab'); T-SQL
        # REPLICATE truncates it. Round first (with the scale arg T-SQL needs).
        out = _tx(_case("challenge_mysql.sql", "my-repeat-float"), "mysql", "tsql")
        assert re.search(r"(?i)ROUND\([^)]*,\s*0\)", out), out

    def test_left_float_rounds(self) -> None:
        # MySQL rounds a float length (LEFT('hello', 2.9) = 'hel'); T-SQL LEFT
        # truncates it.
        out = _tx(_case("challenge_mysql.sql", "my-left-float"), "mysql", "tsql")
        assert re.search(r"(?i)LEFT\(.*ROUND\([^)]*,\s*0\)", out), out


class TestMysqlInsertBounds:
    """MySQL INSERT() returns the original string when the position is 0 or past
    the end; T-SQL STUFF returns NULL there. The MySQL->T-SQL emit guards the
    bounds. Live-verified: out-of-bounds and position-0 keep the original."""

    @pytest.mark.parametrize("keyword", ("my-insert-oob", "my-insert-zeropos"))
    def test_bounds_guarded(self, keyword: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", "tsql")
        assert re.search(r"(?i)CASE\s+WHEN\b.*<\s*1\s+OR\b.*>\s+LEN\(", out), out


class TestMysqlDateArithReturnsDate:
    """MySQL date arithmetic on a DATE returns a DATE ('2020-01-31'); T-SQL
    DATEADD returns a DATETIME ('… 00:00:00'). For a MySQL source with a
    date-only literal base, the T-SQL output is cast back to DATE. Live-verified
    the value/repr matches on all three (ADDDATE, SUBDATE, string + INTERVAL)."""

    @pytest.mark.parametrize(
        "keyword",
        (
            "my-adddate",
            "my-subdate",
            "my-str-plus-interval",
            "my-month-overflow",
            "my-date-add-month",
        ),
    )
    def test_cast_back_to_date(self, keyword: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", "tsql")
        assert re.search(r"(?i)CAST\(\s*DATEADD\(.*\)\s+AS\s+DATE\)", out), out


class TestMysqlBooleanCast:
    """MySQL CAST of a boolean (a comparison) to a character type yields '1'/'0'
    (MySQL booleans are integers); PostgreSQL renders the boolean 't'/'f'. The
    MySQL->PG emit converts the boolean to an integer first. Live-verified '1'."""

    def test_bool_cast_to_char_is_int(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-bool-char"), "mysql", "postgresql")
        assert re.search(r"(?i)CASE\s+WHEN\b.*THEN\s+1\s+ELSE\s+0\s+END", out), out


class TestMysqlAsciiEmpty:
    """MySQL ASCII('') is 0; Oracle/T-SQL return NULL ('' -> NULL). T-SQL can tell
    '' from NULL (faithful CASE, ASCII(NULL) stays NULL); Oracle can't, so
    COALESCE picks the empty-string reading. Live-verified 0 on both."""

    def test_tsql_faithful_case(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-ascii-empty"), "mysql", "tsql")
        assert re.search(
            r"(?i)CASE\s+WHEN\b.*=\s*''\s+THEN\s+0\s+ELSE\s+ASCII", out
        ), out

    def test_oracle_coalesce(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-ascii-empty"), "mysql", "oracle")
        assert "COALESCE(ASCII(" in out and ", 0)" in out, out
