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


class TestExtractFieldTranslation:
    """PG ``EXTRACT``/``DATE_PART`` fields the target's native EXTRACT/DATEPART
    either rejects (Oracle WEEK/QUARTER/DOW) or computes with different semantics
    (WEEK's numbering on MySQL/T-SQL, DOW on every engine). Each maps to a
    value-preserving, ISO-8601 / DATEFIRST- / NLS-independent equivalent
    (live-verified on all four engines: PG week=25 quarter=2, DOW=3)."""

    def test_week_quarter_into_oracle(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-date-part "), "postgresql", "oracle"
        )
        assert "TO_NUMBER(TO_CHAR(DATE '2020-06-15', 'IW'))" in out, out
        assert "TO_NUMBER(TO_CHAR(DATE '2020-06-15', 'Q'))" in out, out
        # no invalid Oracle EXTRACT(WEEK/QUARTER) survives in the SQL itself.
        assert "EXTRACT(" not in _exec_lines(out), out

    def test_week_is_iso_on_mysql_and_tsql(self) -> None:
        my = _tx(
            _case("challenge_postgresql.sql", "pg-date-part "), "postgresql", "mysql"
        )
        assert "WEEK(CAST('2020-06-15' AS DATE), 3)" in my, my
        ts = _tx(
            _case("challenge_postgresql.sql", "pg-date-part "), "postgresql", "tsql"
        )
        assert "DATEPART(ISO_WEEK, CAST('2020-06-15' AS DATE))" in ts, ts

    @pytest.mark.parametrize(
        "target,expected",
        [
            ("mysql", "(DAYOFWEEK(CAST('2020-01-01' AS DATE)) - 1)"),
            (
                "oracle",
                "MOD(MOD(TRUNC(DATE '2020-01-01') - DATE '1970-01-04', 7) + 7, 7)",
            ),
            (
                "tsql",
                "(DATEDIFF(DAY, '19000107', CAST('2020-01-01' AS DATE)) % 7 + 7) % 7",
            ),
        ],
    )
    def test_dow_maps_per_engine(self, target: str, expected: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-extract-dow "), "postgresql", target
        )
        assert expected in out, out

    @pytest.mark.parametrize(
        "case,mysql_expr,tsql_expr",
        [
            # ISO-week edge dates: same mechanism, verified values (PG 1/53/1).
            (
                "pg-week ",
                "WEEK(CAST('2020-01-05' AS DATE), 3)",
                "ISO_WEEK, CAST('2020-01-05'",
            ),
            (
                "pg-week-2016 ",
                "WEEK(CAST('2016-01-01' AS DATE), 3)",
                "ISO_WEEK, CAST('2016-01-01'",
            ),
            (
                "pg-week-jan1 ",
                "WEEK(CAST('2020-01-01' AS DATE), 3)",
                "ISO_WEEK, CAST('2020-01-01'",
            ),
        ],
    )
    def test_iso_week_edge_dates(
        self, case: str, mysql_expr: str, tsql_expr: str
    ) -> None:
        my = _tx(_case("challenge_postgresql.sql", case), "postgresql", "mysql")
        assert mysql_expr in my, my
        ts = _tx(_case("challenge_postgresql.sql", case), "postgresql", "tsql")
        assert tsql_expr in ts, ts


class TestMonthEndFunctions:
    """End-of-month built-ins (T-SQL EOMONTH, MySQL LAST_DAY) map to each
    engine's idiom and agree on the date (2020-02-29). Oracle's DATE type
    renders a 00:00:00 time component — same value, precision-only per the
    2026-07-19 maintainer policy (live-verified on all four engines)."""

    def test_eomonth_into_oracle_and_pg(self) -> None:
        o4 = _tx(_case("challenge_sqlserver.sql", "ts-eomonth "), "tsql", "oracle")
        assert "LAST_DAY(DATE '2020-02-15')" in o4, o4
        pg = _tx(_case("challenge_sqlserver.sql", "ts-eomonth "), "tsql", "postgresql")
        assert "DATE_TRUNC('month', DATE '2020-02-15')" in pg, pg

    def test_eomonth_nested_keeps_month_end(self) -> None:
        o4 = _tx(
            _case("challenge_sqlserver.sql", "ts-eomonth-nested "), "tsql", "oracle"
        )
        assert "ADD_MONTHS(LAST_DAY(DATE '2020-03-01'), -1)" in o4, o4

    def test_mysql_last_day_extract_day(self) -> None:
        ts = _tx(_case("challenge_mysql.sql", "my-lastday-extract "), "mysql", "tsql")
        assert "EOMONTH('2020-02-15')" in ts and "DATEPART(DAY, EOMONTH(" in ts, ts
        o4 = _tx(_case("challenge_mysql.sql", "my-lastday-extract "), "mysql", "oracle")
        assert "EXTRACT(DAY FROM LAST_DAY(DATE '2020-02-15'))" in o4, o4


class TestXmlElementBetweenOracleAndPg:
    """XMLELEMENT is faithful between Oracle and PostgreSQL: PG requires the
    ``NAME`` keyword, Oracle does not, and the element name is quoted on both so
    neither re-folds its case (a PG ``NAME foo`` must stay ``<foo>`` on Oracle,
    not ``<FOO>``). MySQL/T-SQL have no XMLELEMENT — a documented [limit].
    (Live-verified: all three cases return ``<foo>bar</foo>`` on Oracle and PG.)"""

    def test_oracle_source_into_pg_uses_name_keyword(self) -> None:
        pg = _tx(
            _case("challenge_oracle.sql", "ora-xmlelement "), "oracle", "postgresql"
        )
        assert 'XMLELEMENT(NAME "foo", ' in pg, pg

    def test_pg_source_into_oracle_quotes_name(self) -> None:
        # PG's unquoted ``NAME foo`` must become quoted ``"foo"`` on Oracle so it
        # is not upper-folded to FOO.
        o4 = _tx(
            _case("challenge_postgresql.sql", "pg-xmlelement "), "postgresql", "oracle"
        )
        assert 'XMLELEMENT("foo", ' in o4, o4
        assert "NAME" not in _exec_lines(o4), o4


class TestBitAggregatesBetweenMysqlAndPg:
    """BIT_AND/BIT_OR/BIT_XOR aggregates exist on both MySQL and PostgreSQL.
    sqlglot canonicalizes them to BitwiseAndAgg/… whose sql_name is not a real
    function, so the converter recovers the real name; otherwise the gate
    degraded valid MySQL/PG output. Oracle and T-SQL have no bit aggregate — a
    documented [limit]. (Live-verified: my-agg-bit = (0,7,0) on MySQL and PG.)"""

    def test_mysql_source_into_pg(self) -> None:
        pg = _tx(_case("challenge_mysql.sql", "my-agg-bit "), "mysql", "postgresql")
        assert "BIT_AND(x)" in pg and "BIT_OR(x)" in pg and "BIT_XOR(x)" in pg, pg

    def test_pg_source_into_mysql(self) -> None:
        my = _tx(
            _case("challenge_postgresql.sql", "po-agg-bit "), "postgresql", "mysql"
        )
        assert "BIT_AND(x)" in my and "BIT_OR(x)" in my and "BIT_XOR(x)" in my, my


class TestJsonAggregates:
    """JSON aggregates map faithfully across MySQL, PostgreSQL and Oracle (same
    JSON value): PG spells them json_agg / json_object_agg, MySQL/Oracle
    JSON_ARRAYAGG / JSON_OBJECTAGG (Oracle needs KEY..VALUE and a VARCHAR2 key).
    T-SQL has no JSON aggregate, so it degrades to a documented [limit].
    (Live-verified: my-json-agg = ([1,2], {"1":10,"2":20}) on all three.)"""

    def test_mysql_source_into_pg_and_oracle(self) -> None:
        pg = _tx(_case("challenge_mysql.sql", "my-json-agg "), "mysql", "postgresql")
        assert "JSON_AGG(x)" in pg and "JSON_OBJECT_AGG(" in pg, pg
        o4 = _tx(_case("challenge_mysql.sql", "my-json-agg "), "mysql", "oracle")
        assert "JSON_ARRAYAGG(x)" in o4, o4
        assert "VALUE" in o4 and "VARCHAR2" in o4, o4  # Oracle KEY..VALUE, VARCHAR2 key

    def test_pg_source_into_mysql(self) -> None:
        my = _tx(
            _case("challenge_postgresql.sql", "pg-json-aggs "), "postgresql", "mysql"
        )
        assert "JSON_ARRAYAGG(x)" in my and "JSON_OBJECTAGG(" in my, my

    def test_tsql_degrades(self) -> None:
        r = Transpiler().transpile(
            _case("challenge_mysql.sql", "my-json-agg "), source="mysql", target="tsql"
        )
        assert r.warnings and "UNIQUE:" in r.sql, r.sql


class TestAlterModifyColumn:
    """MySQL ALTER TABLE … MODIFY COLUMN c <type> (a column type change) spells
    differently per engine: Oracle MODIFY c, PostgreSQL ALTER COLUMN c TYPE,
    T-SQL ALTER COLUMN c — with the type ported (BIGINT -> Oracle NUMBER).
    sqlglot passes MODIFY COLUMN through unchanged, so it is rewritten here."""

    def _out(self, target: str) -> str:
        return _tx(_case("challenge_mysql.sql", "my-alter-modify "), "mysql", target)

    def test_oracle_modify(self) -> None:
        assert "MODIFY b NUMBER" in self._out("oracle"), self._out("oracle")

    def test_pg_alter_column_type(self) -> None:
        assert "ALTER COLUMN b TYPE BIGINT" in self._out("postgresql")

    def test_tsql_alter_column(self) -> None:
        body = "\n".join(
            ln
            for ln in self._out("tsql").splitlines()
            if not ln.lstrip().startswith("--")
        )
        assert "ALTER COLUMN b BIGINT" in body and "MODIFY" not in body, body


class TestAlterChangeColumn:
    """MySQL ALTER TABLE t CHANGE a x <type> renames AND retypes in one
    statement; it splits into a rename + a type change per engine (Oracle/PG
    RENAME COLUMN, T-SQL EXEC sp_rename), the column being `x` afterward."""

    def _out(self, target: str) -> str:
        return _tx(_case("challenge_mysql.sql", "my-change-column "), "mysql", target)

    def test_oracle_rename_then_modify(self) -> None:
        out = self._out("oracle")
        assert "RENAME COLUMN a TO x" in out and "MODIFY x NUMBER" in out, out

    def test_tsql_sp_rename_then_alter(self) -> None:
        out = self._out("tsql")
        assert "sp_rename 't.a', 'x', 'COLUMN'" in out, out
        assert "ALTER COLUMN x INT" in out, out


class TestAlterSetDefault:
    """MySQL ALTER COLUMN c SET DEFAULT v maps to Oracle MODIFY c DEFAULT v and
    T-SQL ADD CONSTRAINT DF_<t>_<c> DEFAULT v FOR c (a named default
    constraint); PostgreSQL keeps the SET DEFAULT spelling."""

    def _out(self, target: str) -> str:
        return _tx(
            _case("challenge_mysql.sql", "my-alter-set-default "), "mysql", target
        )

    def test_oracle_modify_default(self) -> None:
        assert "MODIFY a DEFAULT 5" in self._out("oracle"), self._out("oracle")

    def test_tsql_named_default_constraint(self) -> None:
        assert "ADD CONSTRAINT DF_t_a DEFAULT 5 FOR a" in self._out("tsql")

    def test_pg_source_set_default(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-set-default "), "postgresql", "oracle"
        )
        assert "MODIFY a DEFAULT 5" in out, out


class TestAlterSuiteBatches:
    """Full ALTER batches: T-SQL SET DEFAULT replaces (drops the current default
    constraint first, error 1781 otherwise) and DROP COLUMN pre-drops the
    dependent default constraint (error 5074 otherwise). Whole batches
    live-verified on Oracle + T-SQL."""

    def test_pg_suite_tsql_set_default_replaces(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-alter-suite "), "postgresql", "tsql"
        )
        assert (
            out.count("sys.default_constraints") >= 2
        ), out  # SET DEFAULT + DROP COLUMN
        assert "ADD CONSTRAINT DF_t_name DEFAULT 'x' FOR name" in out, out

    def test_ora_suite_tsql_drop_column_predrops(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-alter-suite "), "oracle", "tsql")
        assert "sys.default_constraints" in out and "DROP COLUMN nm" in out, out


class TestBitwiseArithmeticPrecedence:
    """Bitwise-vs-arithmetic precedence is not portable (MySQL/Oracle bind
    bitwise looser than +/*; PostgreSQL/T-SQL tighter). A mixed source
    expression is parenthesized explicitly so it can't re-associate."""

    def test_mysql_grouping_preserved_on_tsql(self) -> None:
        for target in ("postgresql", "tsql"):
            out = _tx(_case("challenge_mysql.sql", "my-bit-prec2 "), "mysql", target)
            assert "10 & (6 + 1)" in out and "10 | (2 * 3)" in out, out
            assert "1 << (2 + 1)" in out, out

    def test_pg_grouping_preserved_on_tsql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-bit-prec2 "), "postgresql", "tsql"
        )
        assert "10 & (6 + 1)" in out and "1 << (2 + 1)" in out, out


class TestDateExtractCast:
    """MySQL/T-SQL DATE(x) extracts the date part (drops any time). Unwrapping
    the sqlglot cast wrapper to the bare expression kept the clock on the
    target; an explicit CAST AS DATE preserves the truncation."""

    def test_date_of_timestamp_drops_time(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-ts-to-date "), "mysql", "postgresql")
        assert "CAST(CAST('2020-01-01 14:30' AS TIMESTAMPTZ) AS DATE)" in out, out


class TestLocalTimestamp:
    """Oracle LOCALTIMESTAMP maps to PostgreSQL's niladic keyword (no parens),
    T-SQL SYSDATETIME(), and MySQL CURRENT_TIMESTAMP (a parenthesized
    LOCALTIMESTAMP() is invalid on PG / undefined on T-SQL)."""

    def test_localtimestamp_per_engine(self) -> None:
        case = _case("challenge_oracle.sql", "ora-now-fns ")
        pg = _tx(case, "oracle", "postgresql")
        assert "LOCALTIMESTAMP" in pg and "LOCALTIMESTAMP()" not in pg, pg
        assert "SYSDATETIME()" in _tx(case, "oracle", "tsql")


class TestPkUsingIndex:
    """Oracle's PRIMARY KEY … USING INDEX (backing-index storage detail) is
    stripped for the other engines, which back a PK with an index by default."""

    def test_using_index_stripped(self) -> None:
        case = _case("challenge_oracle.sql", "ora-pk-using-index ")
        for target in ("mysql", "postgresql", "tsql"):
            body = "\n".join(
                ln
                for ln in _tx(case, "oracle", target).splitlines()
                if not ln.lstrip().startswith("--")
            )
            assert "PRIMARY KEY (id)" in body and "USING INDEX" not in body, body


class TestFunctionalIndex:
    """An Oracle expression (function-based) index maps to the MySQL/PostgreSQL
    double-paren form ((expr)); T-SQL has no expression index and degrades."""

    def test_double_parens_on_mysql_pg(self) -> None:
        case = _case("challenge_oracle.sql", "ora-functional-index ")
        assert "ON t ((a * 2))" in _tx(case, "oracle", "mysql")
        assert "ON t ((a * 2))" in _tx(case, "oracle", "postgresql")


class TestSelectIntoCtas:
    """T-SQL / PostgreSQL SELECT … INTO newtable creates a table; Oracle (and
    MySQL) have no such form, so it is rewritten to CREATE TABLE … AS SELECT
    (GLOBAL TEMPORARY for a TEMP / #name target)."""

    def test_tsql_select_into_becomes_ctas(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-select-into "), "tsql", "oracle")
        up = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        ).upper()
        assert "CREATE TABLE DST AS SELECT" in up and " INTO " not in up, up

    def test_pg_temp_select_into_becomes_gtt(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-select-into-ctas "),
            "postgresql",
            "oracle",
        )
        assert "CREATE GLOBAL TEMPORARY TABLE t2 AS SELECT" in out, out


class TestSequenceOptions:
    """Oracle CREATE SEQUENCE one-word negatives (NOCYCLE) map to PostgreSQL /
    T-SQL two-word NO CYCLE, and the ORDER/NOORDER RAC option is dropped."""

    def test_nocycle_and_order_normalized(self) -> None:
        for target in ("postgresql", "tsql"):
            out = _tx(
                _case("challenge_oracle.sql", "ora-sequence-options "), "oracle", target
            )
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "NO CYCLE" in body and "NOCYCLE" not in body, body
            assert "ORDER" not in body, body


class TestJsonColumnType:
    """A MySQL JSON column maps to Oracle CLOB (its JSON type has usage limits)
    and T-SQL NVARCHAR(MAX) (no JSON type pre-2025); PostgreSQL keeps JSON."""

    def test_json_column_maps_per_engine(self) -> None:
        case = _case("challenge_mysql.sql", "my-json-type ")
        assert "data CLOB" in _tx(case, "mysql", "oracle")
        assert "data NVARCHAR(MAX)" in _tx(case, "mysql", "tsql")


class TestAutoIncrementKey:
    """A PostgreSQL SERIAL maps to a MySQL AUTO_INCREMENT column, which MySQL
    requires to be indexed (error 1075); a KEY is added when nothing covers it,
    but not when the column is already a PRIMARY KEY."""

    def test_serial_gets_key_on_mysql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-numtypes "), "postgresql", "mysql"
        )
        assert "AUTO_INCREMENT" in out and "KEY (`g`)" in out, out

    def test_serial_pk_not_double_keyed(self) -> None:
        out = _tx(
            "CREATE TABLE t (id SERIAL PRIMARY KEY, x INT)", "postgresql", "mysql"
        )
        assert out.upper().count("KEY") == 1, out


class TestBitWidthType:
    """MySQL BIT(M) maps to T-SQL BIT with no width (error 2716 on a width),
    consistent with Oracle NUMBER(1) / PG BOOLEAN treating BIT as a boolean."""

    def test_bit_width_dropped_on_tsql(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-bintypes "), "mysql", "tsql")
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "g BIT" in body and "BIT(" not in body, body


class TestFloatDisplayScale:
    """MySQL FLOAT(M,D) is a 4-byte float with a display scale; PostgreSQL and
    T-SQL FLOAT take at most a bit-precision, so it maps to REAL with no width."""

    def test_float_md_maps_to_real_on_tsql(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-numeric "), "mysql", "tsql")
        assert "b REAL" in out and "REAL(" not in out, out


class TestCheckEnforced:
    """MySQL's ENFORCED on a CHECK constraint is the default (the constraint is
    validated); it has no keyword on Oracle/PG/T-SQL, so it is stripped."""

    def test_enforced_stripped(self) -> None:
        for target in ("oracle", "postgresql", "tsql"):
            out = _tx(
                _case("challenge_mysql.sql", "my-check-enforced "), "mysql", target
            )
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "CHECK (a > 0)" in body and "ENFORCED" not in body, body


class TestAlterAddColumnDefault:
    """ADD COLUMN … NOT NULL DEFAULT v: Oracle needs DEFAULT before NOT NULL
    (ORA-30649), and MySQL needs a parenthesized default on TEXT/BLOB columns
    (error 1101). Both are rewritten in the passthrough emitter."""

    def test_tsql_add_reordered_on_oracle(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-alter-add "), "tsql", "oracle")
        assert "DEFAULT 'x' NOT NULL" in out, out

    def test_pg_text_default_parenthesized_on_mysql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-alter-add "), "postgresql", "mysql"
        )
        assert "DEFAULT ('x')" in out, out


class TestAlterDropDefault:
    """ALTER COLUMN a DROP DEFAULT maps to Oracle MODIFY a DEFAULT NULL and to a
    T-SQL dynamic drop of the (auto-named) default constraint via
    sys.default_constraints — a no-op when the column has no default."""

    def test_oracle_modify_default_null(self) -> None:
        out = _tx(
            _case("challenge_mysql.sql", "my-alter-drop-default "), "mysql", "oracle"
        )
        assert "MODIFY a DEFAULT NULL" in out, out

    def test_tsql_dynamic_constraint_drop(self) -> None:
        out = _tx(
            _case("challenge_mysql.sql", "my-alter-drop-default "), "mysql", "tsql"
        )
        assert "sys.default_constraints" in out and "DROP CONSTRAINT" in out, out


class TestPgAlterColumnType:
    """PostgreSQL ALTER COLUMN a [SET DATA] TYPE t maps to Oracle MODIFY a t
    (Oracle has no TYPE keyword); a redundant USING cast IS Oracle's implicit
    conversion and is dropped."""

    def test_alter_type_oracle_modify(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-alter-type "), "postgresql", "oracle"
        )
        assert "MODIFY a NUMBER" in out and "TYPE" not in out.split(";")[-1], out

    def test_alter_using_dropped_on_oracle(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-alter-using "), "postgresql", "oracle"
        )
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "MODIFY a NUMBER" in body and "USING" not in body, body


class TestPgBooleanWordCast:
    """PostgreSQL casts many word spellings to boolean ('t'/'true'/'yes'/'on' ->
    true), which other engines cannot cast to a number or bit. A string-literal
    ::boolean folds to 1/0, so a downstream ::int matches. Live-verified 1."""

    def test_true_word_folds_to_one(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-bool-int-cast "),
            "postgresql",
            "oracle",
        )
        body = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert "CAST(1 AS INT)" in body, body
        assert "'t'" not in body and "'true'" not in body, body


class TestConvertUsingCharset:
    """MySQL CONVERT(x USING charset) is a per-value charset conversion that
    leaves the string value unchanged; no other engine has per-value charsets,
    so it maps to identity (a bare CAST AS CHAR would truncate to CHAR(1))."""

    def test_convert_using_is_identity(self) -> None:
        for target in ("oracle", "postgresql", "tsql"):
            out = _tx(
                _case("challenge_mysql.sql", "my-convert-using2 "), "mysql", target
            )
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            # Unbounded string cast (VARCHAR2(4000)/TEXT/VARCHAR(8000)) preserves
            # the value; it must never be a bare CHAR (truncates to CHAR(1)).
            assert "'2020-06-15 14:30'" in body, body
            assert not re.search(r"(?i)AS CHAR\b", body), body


class TestConcatDateIso:
    """Oracle renders a DATE concatenated to a string via NLS_DATE_FORMAT
    ('01-JAN-20'); MySQL uses ISO 'yyyy-mm-dd'. A DATE-valued CONCAT argument is
    wrapped in TO_CHAR(d, 'YYYY-MM-DD') on Oracle. Live-verified '2020-01-01'."""

    def test_oracle_wraps_date_concat_arg(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-concat-date "), "mysql", "oracle")
        assert "TO_CHAR(DATE '2020-01-01', 'YYYY-MM-DD')" in out, out

    def test_plain_string_concat_untouched(self) -> None:
        assert "TO_CHAR" not in _tx("SELECT CONCAT('a','b') AS r", "mysql", "oracle")


class TestJsonConstructors:
    """JSON_OBJECT / JSON_ARRAY exist on all four engines with different syntax
    (PG json_build_object/array, Oracle KEY..VALUE, T-SQL colon). A boolean stays
    a JSON boolean (PG/Oracle TRUE; T-SQL renders a BIT as true/false) and NULL is
    preserved (Oracle/T-SQL need NULL ON NULL, which sqlglot's T-SQL reader can't
    parse — the gate skips it). Live-verified [1,"a",null,true] on all four."""

    def test_json_object_per_engine(self) -> None:
        case = _case("challenge_mysql.sql", "my-json-object ")
        assert "JSON_BUILD_OBJECT('a', 1" in _tx(case, "mysql", "postgresql")
        assert "'a' VALUE 1" in _tx(case, "mysql", "oracle")
        assert "'a':1" in _tx(case, "mysql", "tsql")

    def test_json_array_boolean_and_null(self) -> None:
        case = _case("challenge_mysql.sql", "my-json-build ")
        pg = _tx(case, "mysql", "postgresql")
        assert "JSON_BUILD_ARRAY(1, 'a', NULL, TRUE)" in pg, pg
        ts = _tx(case, "mysql", "tsql")
        assert "CAST(1 AS BIT)" in ts and "NULL ON NULL" in ts, ts


class TestMonthsBetweenFractional:
    """Oracle MONTHS_BETWEEN is fractional (whole months + (day1-day2)/31, and a
    whole number when both dates are month-ends or the same day-of-month). T-SQL
    has no such function; the exact CASE is emitted (not an integer DATEDIFF
    boundary count). Live-verified 1.83871 and 1.0."""

    def test_tsql_emits_fractional_case(self) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "ora-months-between-val "), "oracle", "tsql"
        )
        assert "EOMONTH" in out and "/ 31.0" in out, out
        assert "DATEDIFF(MONTH" in out, out


class TestTimestampDiffCompletePeriods:
    """MySQL TIMESTAMPDIFF counts COMPLETE periods; T-SQL DATEDIFF counts
    unit-boundary crossings. For month/quarter/year the transpiler drops the
    incomplete final period (DATEADD(unit, boundary, start) > end). A
    DATEDIFF-sourced batch keeps pure boundary counting. Live-verified 1 and 0."""

    def test_month_complete_period_on_tsql(self) -> None:
        ts = _tx(_case("challenge_mysql.sql", "my-timestampdiff-mon "), "mysql", "tsql")
        assert "DATEADD(MONTH, DATEDIFF(MONTH" in ts and "THEN 1 ELSE 0 END" in ts, ts

    def test_datediff_source_stays_boundary(self) -> None:
        # A T-SQL DATEDIFF must NOT gain the complete-period adjustment.
        out = _tx(
            "SELECT DATEDIFF(MONTH, '2020-01-15', '2020-03-10') AS r", "tsql", "tsql"
        )
        assert "CASE WHEN DATEADD" not in out, out


class TestPiMathFunctions:
    """PI() math across engines. T-SQL RADIANS/DEGREES echo the argument's type,
    so an integer arg truncates (RADIANS(180)=3) — the integer is cast to FLOAT.
    PostgreSQL TRUNC/ROUND have no (double precision, int) overload, so a double
    value like PI() is cast to NUMERIC. Live-verified on all four engines."""

    def test_radians_integer_arg_cast_to_float(self) -> None:
        ts = _tx(_case("challenge_mysql.sql", "my-pi-vals "), "mysql", "tsql")
        assert "RADIANS(CAST(180 AS FLOAT))" in ts, ts

    def test_pg_trunc_round_double_cast_to_numeric(self) -> None:
        pg = _tx(_case("challenge_mysql.sql", "my-pi-fns "), "mysql", "postgresql")
        assert "TRUNC(CAST(PI() AS NUMERIC), 4)" in pg, pg
        assert "ROUND(CAST(PI() AS NUMERIC), 4)" in pg, pg


class TestLastDayAndNames:
    """LAST_DAY / DAYNAME / MONTHNAME (MySQL) across engines. The date-name
    functions wrap a bare ISO string as an ANSI ``DATE`` literal (else Oracle/PG
    reject it) and use the FM-trimmed, init-capped name model so a lone month/day
    name matches MySQL's 'June'/'Monday' instead of Oracle's padded 'JUNE     '.
    Live-verified 2020-02-29, Monday, June on all four engines."""

    def _out(self, target: str) -> str:
        return _tx(_case("challenge_mysql.sql", "my-last-day-name "), "mysql", target)

    def test_last_day_forms(self) -> None:
        assert "EOMONTH('2020-02-15')" in self._out("tsql")
        assert "LAST_DAY(DATE '2020-02-15')" in self._out("oracle")
        assert "DATE_TRUNC('month', DATE '2020-02-15')" in self._out("postgresql")

    def test_month_and_day_names_trimmed(self) -> None:
        ora = self._out("oracle")
        assert "TO_CHAR(DATE '2020-06-15', 'fmDay')" in ora, ora
        assert "TO_CHAR(DATE '2020-06-15', 'FMMonth')" in ora, ora
        pg = self._out("postgresql")
        assert "TO_CHAR(DATE '2020-06-15', 'FMDay')" in pg, pg
        assert "TO_CHAR(DATE '2020-06-15', 'FMMonth')" in pg, pg


class TestJsonPathExtraction:
    """JSON_VALUE(doc, path) and JSON_QUERY(doc, path) (Oracle/T-SQL scalar and
    object extraction). MySQL has JSON_VALUE natively but routes JSON_QUERY
    through JSON_EXTRACT; PostgreSQL <17 has neither and uses the SQL/JSON path
    engine (JSONB_PATH_QUERY_FIRST). Live-verified '1' and '[1]' on all four."""

    def test_json_value_per_engine(self) -> None:
        case = _case("challenge_oracle.sql", "ora-json-value ")
        pg = _tx(case, "oracle", "postgresql")
        assert (
            "JSONB_PATH_QUERY_FIRST(CAST('{\"a\":1}' AS JSONB), '$.a') #>> '{}'" in pg
        ), pg
        assert "JSON_VALUE('{\"a\":1}', '$.a')" in _tx(case, "oracle", "mysql")
        assert "JSON_VALUE('{\"a\":1}', '$.a')" in _tx(case, "oracle", "tsql")

    def test_json_query_object_form(self) -> None:
        case = _case("challenge_oracle.sql", "ora-json-x ")
        # MySQL has no JSON_QUERY -> JSON_EXTRACT; PG -> path engine (no #>>).
        my = _tx(case, "oracle", "mysql")
        assert "JSON_EXTRACT('{\"a\":[1]}', '$.a')" in my, my
        pg = _tx(case, "oracle", "postgresql")
        assert "JSONB_PATH_QUERY_FIRST(CAST('{\"a\":[1]}' AS JSONB), '$.a')" in pg, pg


class TestDateTruncMonth:
    """PG date_trunc parses to TimestampTrunc (fake sql_name); it is canonicalized
    to DATE_TRUNC and mapped per engine — Oracle TRUNC(ts,'MM'), T-SQL
    DATETRUNC(month, …), MySQL DATE_FORMAT. Also exercises the Oracle
    TIMESTAMP-literal seconds padding. (Live-verified 2020-05-01 on all four.)"""

    def test_pg_month_trunc_per_engine(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-date-trunc ")
        o4 = _tx(case, "postgresql", "oracle")
        assert "TRUNC(" in o4 and "'MM'" in o4, o4
        assert "TIMESTAMP '2020-05-17 10:00:00'" in o4, o4  # seconds padded
        ts = _tx(case, "postgresql", "tsql")
        assert "DATETRUNC(month," in ts, ts
        my = _tx(case, "postgresql", "mysql")
        assert "DATE_FORMAT(" in my and "%Y-%m-01" in my, my


class TestDateFormatMasks:
    """TO_CHAR(date, mask) / TO_TIMESTAMP(str, mask): sqlglot canonicalizes the
    mask to python strftime; the emitter translates it to each engine's model
    (Oracle/PG ``YYYY-MM-DD``, MySQL ``%Y-%m-%d`` with bare literals, T-SQL .NET
    ``yyyy-MM-dd``) and spells TO_CHAR / DATE_FORMAT / FORMAT. A constant
    ISO-shaped string parses to a fixed value (ANSI literal / CAST).
    (Live-verified 2020-06-15T14:30:45 and the .123 fractional on all four.)"""

    def test_tochar_iso_formatting(self) -> None:
        case = _case("challenge_oracle.sql", "ora-tochar-iso ")
        my = _tx(case, "oracle", "mysql")
        assert "DATE_FORMAT(" in my and "%Y-%m-%dT%H:%i:%s" in my, my
        ts = _tx(case, "oracle", "tsql")
        assert "FORMAT(" in ts and "yyyy-MM-dd" in ts, ts
        pg = _tx(case, "oracle", "postgresql")
        assert "TO_CHAR(" in pg and 'YYYY-MM-DD"T"HH24:MI:SS' in pg, pg

    def test_to_timestamp_fractional(self) -> None:
        case = _case("challenge_oracle.sql", "ora-to-timestamp ")
        my = _tx(case, "oracle", "mysql")
        assert "DATETIME(6)" in my, my  # keeps the .123 fractional
        pg = _tx(case, "oracle", "postgresql")
        assert "TIMESTAMP '2020-01-01 10:00:00.123'" in pg, pg

    def test_mysql_date_format_wraps_string_value(self) -> None:
        # DATE_FORMAT('2020-05-17', …): the bare ISO string is wrapped as a DATE
        # so Oracle/PG TO_CHAR (which reject a string) work.
        case = _case("challenge_mysql.sql", "my-date-format ")
        o4 = _tx(case, "mysql", "oracle")
        assert "TO_CHAR(DATE '2020-05-17', 'YYYY/MM/DD')" in o4, o4
        ts = _tx(case, "mysql", "tsql")
        assert "FORMAT(CAST('2020-05-17' AS DATE), 'yyyy/MM/dd')" in ts, ts

    def test_bare_letter_mask_degrades(self) -> None:
        # A MySQL mask with a bare-letter literal (%Y-%m-%dT…) or a locale name
        # (%W) cannot round-trip unquoted — it must degrade, not ship wrong.
        r = Transpiler().transpile(
            _case("challenge_mysql.sql", "my-dateformat-iso "),
            source="mysql",
            target="oracle",
        )
        assert r.warnings and "UNIQUE:" in r.sql, r.sql

    def test_number_format_mask(self) -> None:
        # T-SQL FORMAT(num, 'N2') -> Oracle/PG TO_CHAR FM mask, MySQL FORMAT(n, 2).
        case = _case("challenge_sqlserver.sql", "ts-format-number ")
        o4 = _tx(case, "tsql", "oracle")
        assert "TO_CHAR(1234.5, 'FM" in o4 and "D00')" in o4, o4
        my = _tx(case, "tsql", "mysql")
        assert "FORMAT(1234.5, 2)" in my, my

    def test_currency_number_mask_degrades(self) -> None:
        # A currency mask (L) has no cross-engine equivalent — degrade, not
        # ship a wrong DATE_FORMAT.
        r = Transpiler().transpile(
            "SELECT TO_CHAR(1234.5, 'L9G999D99') AS r", source="oracle", target="mysql"
        )
        assert r.warnings and "UNIQUE:" in r.sql, r.sql


class TestTsqlIntToDatetime:
    """T-SQL ``CAST(n AS DATETIME)`` reads n as days since the 1900-01-01 epoch;
    no other engine has that implicit conversion, so it becomes date arithmetic
    ``DATE '1900-01-01' + n`` (live-verified 1900-01-02 on Oracle and PG)."""

    def test_int_to_datetime_epoch(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-cast-int-datetime ")
        o4 = _tx(case, "tsql", "oracle")
        assert "DATE '1900-01-01' + 1" in o4, o4
        pg = _tx(case, "tsql", "postgresql")
        assert "AS DATE) + 1" in pg, pg

    def test_datalength_byte_length(self) -> None:
        # DATALENGTH(x) is the byte length -> LENGTHB / OCTET_LENGTH; the
        # VARBINARY cast is unwrapped.
        case = _case("challenge_sqlserver.sql", "ts-binary-length ")
        assert "LENGTHB('hello')" in _tx(case, "tsql", "oracle")
        assert "OCTET_LENGTH('hello')" in _tx(case, "tsql", "postgresql")

    def test_money_cast_and_currency_string(self) -> None:
        # MONEY -> NUMBER/NUMERIC(19,4); CONVERT(MONEY, '$12.99') strips $/commas.
        case = _case("challenge_sqlserver.sql", "ts-cast-money ")
        o4 = _tx(case, "tsql", "oracle")
        assert "CAST(12.99 AS NUMBER(19,4))" in o4, o4
        assert "REPLACE(REPLACE('$12.99', '$', ''), ',', '')" in o4, o4

    def test_mysql_cast_char_to_string_type(self) -> None:
        # MySQL CAST(x AS CHAR) (no length) -> a target string type, not a bare
        # length-less CHAR (which Oracle rejects).
        case = _case("challenge_mysql.sql", "my-cast-num-char ")
        assert "VARCHAR2(4000)" in _tx(case, "mysql", "oracle")
        assert "AS TEXT)" in _tx(case, "mysql", "postgresql")

    def test_mysql_cast_to_int_rounds(self) -> None:
        # MySQL CAST(x AS SIGNED) rounds; Oracle INTEGER rounds, T-SQL truncates
        # so ROUND is wrapped -- including for a negated literal (-3.99).
        case = _case("challenge_mysql.sql", "my-round-cast ")
        assert "CAST(-3.99 AS INTEGER)" in _tx(case, "mysql", "oracle")
        assert "CAST(ROUND(-3.99, 0) AS BIGINT)" in _tx(case, "mysql", "tsql")

    def test_mysql_cast_datetime_iso_literal(self) -> None:
        # CAST(iso-string AS DATETIME) -> Oracle ANSI DATE/TIMESTAMP literal (a
        # bare CAST to TIMESTAMP applies NLS and fails).
        case = _case("challenge_mysql.sql", "my-cast-datetime ")
        assert "DATE '2020-01-01'" in _tx(case, "mysql", "oracle")

    def test_mysql_year_type_folds_to_integer(self) -> None:
        # MySQL YEAR (no cross-engine type) folds a literal to its integer year
        # with the 2-digit century rule ('99' -> 1999).
        o4 = _tx(_case("challenge_mysql.sql", "my-cast-year "), "mysql", "oracle")
        assert "2020, 2020, 1999" in o4, o4


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


class TestTruncateRestartIdentity:
    """PG TRUNCATE … RESTART IDENTITY / CASCADE: RESTART IDENTITY is the default
    on MySQL/Oracle/T-SQL (strip it), CASCADE is kept on Oracle but carriered on
    MySQL/T-SQL. Live-verified valid on all targets."""

    @pytest.mark.parametrize("target", ("mysql", "oracle", "tsql"))
    def test_restart_identity_stripped(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-truncate-restart"),
            "postgresql",
            target,
        )
        sql_only = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert not re.search(r"(?i)RESTART\s+IDENTITY", sql_only), out

    def test_cascade_kept_on_oracle_stripped_elsewhere(self) -> None:
        ora = _tx("TRUNCATE TABLE t RESTART IDENTITY CASCADE", "postgresql", "oracle")
        assert re.search(r"(?i)TRUNCATE\s+TABLE\s+t\s+CASCADE", ora), ora
        res = Transpiler().transpile(
            "TRUNCATE TABLE t RESTART IDENTITY CASCADE",
            source="postgresql",
            target="mysql",
        )
        assert re.search(r"(?i)UNIQUE:.*CASCADE", res.sql) and res.warnings, res.sql


class TestIndexNullsOrderCarrier:
    """NULLS FIRST/LAST on an index column has no equivalent on Oracle (ORA-00907
    in an index), T-SQL or MySQL; the drop (physical null-order only, no query
    result impact) is surfaced as a carrier + warning, not dropped silently."""

    @pytest.mark.parametrize("target", ("oracle", "tsql", "mysql"))
    def test_carrier_and_warning(self, target: str) -> None:
        res = Transpiler().transpile(
            _case("challenge_postgresql.sql", "postgresql-drop2-NULLS"),
            source="postgresql",
            target=target,
        )
        assert re.search(r"(?i)UNIQUE:.*NULLS\s+FIRST/LAST", res.sql), res.sql
        assert res.warnings, "expected a loss warning"

    def test_plain_index_has_no_carrier(self) -> None:
        res = Transpiler().transpile(
            "CREATE INDEX ix ON t (a)", source="postgresql", target="oracle"
        )
        assert "UNIQUE:" not in res.sql, res.sql


class TestMysqlComments:
    """MySQL column and table COMMENT materialize on PG/Oracle (COMMENT ON
    COLUMN / COMMENT ON TABLE) rather than being dropped silently."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_column_comment_materializes(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "mysql-drop-'note'"), "mysql", target)
        assert re.search(r"(?i)COMMENT\s+ON\s+COLUMN\s+t\.a\s+IS\s+'note'", out), out

    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_table_comment_materializes(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "mysql-drop2-my"), "mysql", target)
        assert re.search(r"(?i)COMMENT\s+ON\s+TABLE\s+t\s+IS\s+'my table'", out), out


class TestMysqlSqlCalcFoundRows:
    """MySQL SQL_CALC_FOUND_ROWS has no equivalent on other engines; the drop is
    surfaced as a carrier + warning (mirrored by the no-silent-loss scan) rather
    than dropped silently. The underlying SELECT stays valid."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql", "tsql"))
    def test_carrier_and_warning(self, target: str) -> None:
        res = Transpiler().transpile(
            _case("challenge_mysql.sql", "mysql-qdrop-SQL_CALC_FOU"),
            source="mysql",
            target=target,
        )
        assert "SQL_CALC_FOUND_ROWS" in res.sql, res.sql  # in the carrier comment
        assert res.warnings, "expected a value/loss warning"

    def test_plain_select_has_no_carrier(self) -> None:
        res = Transpiler().transpile("SELECT x FROM t", source="mysql", target="tsql")
        assert "UNIQUE:" not in res.sql, res.sql


class TestMysqlDatetimePrecision:
    """MySQL DATETIME(n)/TIMESTAMP(n) carry fractional-seconds precision. T-SQL
    DATETIME takes no width (error 2716), so DATETIME(n) -> DATETIME2(n); Oracle
    TIMESTAMP's precision goes inside the type (TIMESTAMP(n) WITH TIME ZONE, not
    ...WITH TIME ZONE(n)). Live-verified valid on all targets."""

    def test_tsql_datetime_precision_uses_datetime2(self) -> None:
        out = _tx(
            _case("challenge_mysql.sql", "my-datetime-precision"), "mysql", "tsql"
        )
        assert re.search(r"(?i)DATETIME2\(6\)", out), out

    def test_oracle_timestamp_precision_inside_type(self) -> None:
        out = _tx(
            _case("challenge_mysql.sql", "my-datetime-precision"), "mysql", "oracle"
        )
        assert re.search(r"(?i)TIMESTAMP\(3\)\s+WITH\s+TIME\s+ZONE", out), out

    def test_tsql_bare_datetime_unchanged(self) -> None:
        # A DATETIME with no precision must stay DATETIME (no width, no churn).
        out = _tx("CREATE TABLE t (a DATETIME)", "mysql", "tsql")
        assert re.search(r"(?i)\bDATETIME\b", out) and "DATETIME2" not in out.upper()


class TestOracleTimestampCast:
    """Oracle CAST(x AS TIMESTAMP): MySQL has no TIMESTAMP cast target (1064) so
    it must be DATETIME, and T-SQL TIMESTAMP is a rowversion (binary), not a
    datetime, so it must be DATETIME2 to keep the value."""

    @pytest.mark.parametrize(
        "target,ty", [("mysql", "DATETIME"), ("tsql", "DATETIME2")]
    )
    def test_timestamp_cast_maps(self, target: str, ty: str) -> None:
        out = _tx("SELECT CAST(SYSDATE AS TIMESTAMP) AS r", "oracle", target)
        assert re.search(rf"(?i)CAST\(.*AS {ty}\)", out), out
        assert not re.search(r"(?i)AS\s+TIMESTAMP\)", out), out


class TestOracleAddMonthsPgTypedLiteral:
    """Oracle ADD_MONTHS(DATE 'lit', n) on a PG target: the ISO date literal must
    be typed (DATE '…'), else PG's DATE_TRUNC has no unique overload for an
    untyped string ("date_trunc(unknown, unknown) is not unique"). Live-verified
    2020-02-29 (sticky last-day). A column operand is left untyped."""

    def test_pg_types_the_date_literal(self) -> None:
        out = _tx(
            "SELECT ADD_MONTHS(DATE '2020-01-31', 1) AS r", "oracle", "postgresql"
        )
        assert re.search(r"(?i)DATE_TRUNC\('month',\s*DATE\s*'", out), out

    def test_pg_leaves_a_column_untyped(self) -> None:
        # A column operand needs no DATE wrapper (it is already typed).
        out = _tx("SELECT ADD_MONTHS(d, 1) AS r FROM t", "oracle", "postgresql")
        assert re.search(r"(?i)DATE_TRUNC\('month',\s*d\)", out), out


class TestOracleBitand:
    """Oracle BITAND(a, b) is a bitwise AND; the other engines (including PG,
    which has no BITAND) spell it with the & operator. Live-verified 2."""

    @pytest.mark.parametrize("target", ("mysql", "postgresql", "tsql"))
    def test_bitand_becomes_operator(self, target: str) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-bitand"), "oracle", target)
        sql_only = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert re.search(r"\(\s*5\s*&\s*3\s*\)", sql_only), out
        assert not re.search(r"(?i)BITAND\s*\(", sql_only), out


class TestMysqlTwoArgAtan:
    """MySQL ATAN(y, x) is the 2-argument arctangent (= ATAN2); Oracle/PG use
    ATAN2 and T-SQL uses ATN2. Live-verified pi/4."""

    @pytest.mark.parametrize(
        "target,fn", [("oracle", "ATAN2"), ("postgresql", "ATAN2"), ("tsql", "ATN2")]
    )
    def test_two_arg_atan_maps(self, target: str, fn: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-trig"), "mysql", target)
        assert re.search(rf"(?i){fn}\(\s*1,\s*1\s*\)", out), out


class TestOracleExceptionConditionMapsToPg:
    """Oracle predefined exception names differ from PL/pgSQL condition names
    (ZERO_DIVIDE vs division_by_zero); emitting the Oracle spelling verbatim is
    rejected by PostgreSQL. The PG emitter maps the standard ones."""

    def test_zero_divide_maps_to_division_by_zero(self) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "ora-zero-divide"), "oracle", "postgresql"
        )
        assert re.search(r"(?i)WHEN\s+division_by_zero\s+THEN", out), out
        assert not re.search(r"(?i)WHEN\s+ZERO_DIVIDE", out), out


class TestOracleDecodeNullSafe:
    """Oracle DECODE uses NULL-safe equality (a NULL search matches a NULL
    subject), unlike SQL '=' where NULL = NULL is unknown. The DECODE_CASE emit
    spells a NULL search as ``subject IS NULL`` (not ``= NULL``). Live-verified
    'match', not 'no'."""

    @pytest.mark.parametrize("target", ("mysql", "postgresql", "tsql"))
    def test_null_search_is_null(self, target: str) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-decode-null"), "oracle", target)
        assert re.search(r"(?i)WHEN\s+NULL\s+IS\s+NULL\s+THEN", out), out
        assert not re.search(r"(?i)WHEN\s+NULL\s*=\s*NULL", out), out

    def test_nonnull_search_uses_equality(self) -> None:
        # A non-NULL search keeps plain '=' (no IS NULL rewrite).
        out = _tx("SELECT DECODE(x, 1, 'a', 'b') AS r FROM t", "oracle", "tsql")
        assert re.search(r"(?i)WHEN\s+x\s*=\s*1\s+THEN", out), out


class TestOracleCastIntRounds:
    """Oracle CAST-to-integer ROUNDS (CAST('3.9' AS INT) = 4); MySQL's
    CAST(... AS SIGNED) truncates a string. The Oracle->MySQL emit rounds first
    so the value matches (live-verified: 4, not 3)."""

    def test_mysql_rounds_the_cast(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "cast-int-edge"), "oracle", "mysql")
        assert "CAST(ROUND('3.9') AS SIGNED)" in out, out


class TestTsqlCastIntRounds:
    """PG/MySQL CAST-to-integer round a numeric literal half-away-from-zero
    (CAST(2.7 AS INT) = 3, 7.5 -> 8); T-SQL CAST truncates. The emit wraps
    ROUND(x, 0) on a T-SQL target (T-SQL ROUND is half-away-from-zero too).
    Live-verified 3/8, not 2/7."""

    @pytest.mark.parametrize(
        "src_file,src,keyword",
        [
            ("challenge_postgresql.sql", "postgresql", "pg-cast-int"),
            ("challenge_postgresql.sql", "postgresql", "pg-cast-round-half"),
            ("challenge_mysql.sql", "mysql", "my-cast-int"),
        ],
    )
    def test_tsql_rounds_the_cast(self, src_file: str, src: str, keyword: str) -> None:
        out = _tx(_case(src_file, keyword), src, "tsql")
        assert re.search(r"(?i)CAST\(\s*ROUND\(.*,\s*0\)\s*AS\b", out), out

    def test_integer_literal_cast_not_wrapped(self) -> None:
        # A non-fractional literal must not get a ROUND wrapper (no churn).
        out = _tx("SELECT CAST(5 AS INT) AS r", "postgresql", "tsql")
        assert "ROUND" not in out.upper(), out


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


class TestGreatestLeastDropsNullFromPg:
    """PG/T-SQL GREATEST/LEAST ignore NULL args (GREATEST(1, NULL, 3) = 3);
    MySQL/Oracle propagate NULL. A literal NULL arg is dropped on those targets
    so the max/min over the survivors matches. Live-verified 3, not NULL."""

    @pytest.mark.parametrize("target", ("mysql", "oracle"))
    def test_literal_null_dropped(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-greatest-null"), "postgresql", target
        )
        # GREATEST(1, 3) proves the NULL arg was dropped (it is not in the call).
        assert re.search(r"(?i)GREATEST\(\s*1,\s*3\s*\)", out), out


class TestSingleArgCoalesce:
    """A 1-arg COALESCE(x) is its argument; Oracle (ORA-00938) and T-SQL reject
    a single-argument COALESCE, so it is reduced to the argument."""

    @pytest.mark.parametrize("target", ("oracle", "tsql"))
    def test_reduced_to_argument(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-coalesce-single"), "mysql", target)
        sql_only = "\n".join(
            ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
        )
        assert not re.search(r"(?i)COALESCE\s*\(", sql_only), out


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


class TestReplaceCaseSensitive:
    """MySQL/Oracle/PG REPLACE matches case-sensitively; T-SQL uses the subject's
    (case-insensitive) collation, so REPLACE('AbCaBc','a','X') would also replace
    the 'A'. Force a BIN2 collation on a literal subject. Live-verified 'AbCXBc'."""

    def test_tsql_literal_subject_is_binary(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-replace-case "), "mysql", "tsql")
        assert "REPLACE('AbCaBc' COLLATE Latin1_General_BIN2, 'a', 'X')" in out, out


class TestInstrCaseSensitive:
    """Oracle/PostgreSQL INSTR searches case-sensitively, but MySQL's and T-SQL's
    default collations are case-insensitive (INSTR('aAaA','A') = 1 not 2). Force a
    binary / BIN2 collation on the haystack so the match position matches the
    source. Live-verified 2 on MySQL and T-SQL."""

    def test_forces_case_sensitive_haystack(self) -> None:
        case = _case("challenge_oracle.sql", "ora-instr-case ")
        assert "BINARY 'aAaA'" in _tx(case, "oracle", "mysql")
        assert "'aAaA' COLLATE Latin1_General_BIN2" in _tx(case, "oracle", "tsql")


class TestTopWithTies:
    """T-SQL TOP n WITH TIES also returns rows tying the last one. PG (13+) and
    Oracle carry it as FETCH FIRST n ROWS WITH TIES (a plain LIMIT would silently
    drop the ties); MySQL has no equivalent, so it keeps LIMIT + a documented
    carrier warning. Live-verified [(1,), (1,)] on PG/Oracle."""

    def test_pg_and_oracle_fetch_with_ties(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-top-with-ties ")
        assert "FETCH FIRST 1 ROWS WITH TIES" in _tx(case, "tsql", "postgresql")
        assert "FETCH FIRST 1 ROWS WITH TIES" in _tx(case, "tsql", "oracle")

    def test_mysql_documents_dropped_ties(self) -> None:
        case = _case("challenge_sqlserver.sql", "ts-top-with-ties ")
        result = Transpiler().transpile(case, source="tsql", target="mysql")
        assert result.warnings, "MySQL WITH TIES loss must warn"
        assert "WITH TIES" in result.sql and "LIMIT 1" in result.sql, result.sql


class TestOracleIdentityOptions:
    """Oracle IDENTITY (START WITH/INCREMENT BY/MAXVALUE/CYCLE) has no MySQL
    per-column form — AUTO_INCREMENT always starts at 1 / steps by 1. Emit the
    keyed AUTO_INCREMENT plus a documented carrier + warning rather than silently
    resetting the sequence."""

    def test_mysql_carries_dropped_options(self) -> None:
        case = _case("challenge_oracle.sql", "ora-identity-opts ")
        result = Transpiler().transpile(case, source="oracle", target="mysql")
        assert result.warnings, "dropped IDENTITY options must warn"
        assert "UNIQUE:" in result.sql, result.sql
        # AUTO_INCREMENT column must still be keyed (the carrier's "UNIQUE:" is
        # not a key).
        assert "KEY (`a`)" in result.sql, result.sql


class TestTablesample:
    """TABLESAMPLE re-spells natively on PG/T-SQL (TABLESAMPLE) and Oracle
    (SAMPLE); MySQL has no row sampling, so it degrades to a documented carrier +
    warning instead of silently returning every row."""

    def test_pg_sample_to_tsql_and_oracle(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-tablesample ")
        assert "TABLESAMPLE (50 PERCENT)" in _tx(case, "postgresql", "tsql")
        assert "SAMPLE (50)" in _tx(case, "postgresql", "oracle")

    def test_mysql_degrades_with_warning(self) -> None:
        case = _case("challenge_postgresql.sql", "pg-tablesample ")
        result = Transpiler().transpile(case, source="postgresql", target="mysql")
        assert result.warnings, "dropped TABLESAMPLE must warn"
        assert "UNIQUE:" in result.sql and "TABLESAMPLE" in result.sql, result.sql


class TestToNumberScientific:
    """Oracle TO_NUMBER of a scientific-notation string ('1.234E2') can't CAST to
    a T-SQL DECIMAL (error 8114); FLOAT parses the exponent. Live-verified 123.4."""

    def test_tsql_uses_float_for_exponent(self) -> None:
        out = _tx(_case("challenge_oracle.sql", "ora-to-number-sci "), "oracle", "tsql")
        assert "CAST('1.234E2' AS FLOAT)" in out, out


class TestPgBooleanToText:
    """PostgreSQL renders a boolean cast to text as 'true'/'false'; MySQL has no
    boolean text and would give '1'/'0'. Emit CASE WHEN <bool> THEN 'true' ELSE
    'false' for a comparison or a true/false literal. Live-verified 'true'."""

    def test_bool_literal_to_text(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-bool-text2 "), "postgresql", "mysql"
        )
        assert "CASE WHEN TRUE THEN 'true' ELSE 'false' END" in out, out

    def test_comparison_to_text(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-bool-repr "), "postgresql", "mysql"
        )
        assert "CASE WHEN 1 > 0 THEN 'true' ELSE 'false' END" in out, out


class TestPgBooleanCastFolds:
    """PostgreSQL word-spelled boolean casts ('true'/'t'/'1'/'yes'/'off') fold to
    1/0 on Oracle/T-SQL (which have no boolean text). Live-verified (1,1,1,1) and
    (1,1,0,1) — True==1, False==0."""

    def test_bool_literals_fold_to_ints(self) -> None:
        for target in ("oracle", "tsql"):
            out = _tx(
                _case("challenge_postgresql.sql", "pg-cast-bool2 "),
                "postgresql",
                target,
            )
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "1, 1, 0, 1" in body, body


class TestTsqlFracSeconds:
    """T-SQL CAST(... AS DATETIME2/DATETIME) over a fractional-second string maps
    to an Oracle TIMESTAMP literal (a bare string tripped ORA-01843). Live-verified
    10:20:30.123456 / .123000 on Oracle."""

    def test_oracle_timestamp_literal(self) -> None:
        out = _tx(
            _case("challenge_sqlserver.sql", "ts-frac-seconds "), "tsql", "oracle"
        )
        assert "TIMESTAMP '2020-01-01 10:20:30.1234567'" in out, out
        assert "TIMESTAMP '2020-01-01 10:20:30.123'" in out, out


class TestTsqlDateAddEomonth:
    """T-SQL DATEADD / EOMONTH over date-string literals map to each engine's
    idiom (ADD_MONTHS/LAST_DAY on Oracle, DATE_ADD/LAST_DAY on MySQL, interval
    arithmetic on PG) with the literal qualified as a DATE. Live-verified
    2020-02-29 / 2020-01-02 / 2020-02-29 on every target."""

    def test_oracle_uses_add_months_and_last_day(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-dateadd "), "tsql", "oracle")
        assert "ADD_MONTHS(DATE '2020-01-31', 1)" in out, out
        assert "LAST_DAY(DATE '2020-02-15')" in out, out

    def test_mysql_uses_date_add(self) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-dateadd "), "tsql", "mysql")
        assert "DATE_ADD('2020-01-31', INTERVAL 1 MONTH)" in out, out
        assert "LAST_DAY('2020-02-15')" in out, out


class TestDateAddQualifiesDateLiteral:
    """MySQL's DATE_ADD reads a bare '2020-01-01' string as a date, but PG reads
    it as an interval and Oracle rejects the implicit cast. A date-only literal
    base is qualified as an ANSI DATE literal so the interval add runs (verified
    2020-01-08 on both; midnight on the datetime-typed targets)."""

    def test_pg_and_oracle_qualify_the_literal(self) -> None:
        case = _case("challenge_mysql.sql", "my-date-add-interval ")
        assert "DATE '2020-01-01' + INTERVAL '7 DAY'" in _tx(
            case, "mysql", "postgresql"
        )
        ora = _tx(case, "mysql", "oracle")
        assert "DATE '2020-01-01' + NUMTODSINTERVAL(7, 'DAY')" in ora, ora


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

    def test_concat_bool_is_int(self) -> None:
        # CONCAT(TRUE, FALSE) is '10' on MySQL; PG must emit CONCAT(1, 0), not
        # CONCAT(TRUE, FALSE) (which is 'tf').
        out = _tx(_case("challenge_mysql.sql", "my-concat-bool"), "mysql", "postgresql")
        assert "CONCAT(1, 0)" in out, out


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

    def test_pg_source_tsql_case(self) -> None:
        # PostgreSQL ASCII('') is also 0 — same recovery on a PG source.
        out = _tx(
            _case("challenge_postgresql.sql", "pg-ascii-empty"), "postgresql", "tsql"
        )
        assert re.search(
            r"(?i)CASE\s+WHEN\b.*=\s*''\s+THEN\s+0\s+ELSE\s+ASCII", out
        ), out

    def test_pg_source_oracle_coalesce(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-ascii-empty"), "postgresql", "oracle"
        )
        assert "COALESCE(ASCII(" in out and ", 0)" in out, out


class TestMysqlLocateEmpty:
    """MySQL LOCATE/INSTR with an empty needle returns 1; Oracle INSTR returns
    NULL ('' -> NULL) and T-SQL CHARINDEX returns 0. Recover the 1 (Oracle
    COALESCE(INSTR, 1); T-SQL CASE WHEN needle = '' THEN 1). Live-verified."""

    @pytest.mark.parametrize("keyword", ("my-locate-empty", "my-locate-empty2"))
    def test_oracle_coalesces_to_one(self, keyword: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", "oracle")
        assert re.search(r"(?i)COALESCE\(\s*INSTR\(.*\)\s*,\s*1\)", out), out

    @pytest.mark.parametrize("keyword", ("my-locate-empty", "my-locate-empty2"))
    def test_tsql_case_to_one(self, keyword: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", "tsql")
        assert re.search(r"(?i)CASE\s+WHEN\b.*=\s*''\s+THEN\s+1", out), out

    @pytest.mark.parametrize("keyword", ("pg-position-empty", "pg-strpos-empty"))
    def test_pg_oracle_coalesces_to_one(self, keyword: str) -> None:
        # PostgreSQL POSITION/STRPOS with an empty needle also returns 1.
        out = _tx(_case("challenge_postgresql.sql", keyword), "postgresql", "oracle")
        assert re.search(r"(?i)COALESCE\(\s*INSTR\(.*\)\s*,\s*1\)", out), out

    @pytest.mark.parametrize("keyword", ("pg-position-empty", "pg-strpos-empty"))
    def test_pg_tsql_case_to_one(self, keyword: str) -> None:
        out = _tx(_case("challenge_postgresql.sql", keyword), "postgresql", "tsql")
        assert re.search(r"(?i)CASE\s+WHEN\b.*=\s*''\s+THEN\s+1", out), out


class TestMysqlStringPlusIsArithmetic:
    """MySQL '+' is always arithmetic, so '5' + '5' is 10; T-SQL '+' on strings
    concatenates ('55'). For a MySQL source adding numeric string literals, cast
    them so T-SQL does the arithmetic. Live-verified 10.0 (not '55')."""

    def test_numeric_string_add_casts(self) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-strnum-add"), "mysql", "tsql")
        assert "CAST('5' AS FLOAT) + CAST('5' AS FLOAT)" in out, out


class TestStringPlusNumberStaysArithmetic:
    """A T-SQL/Oracle '+' with one string and one *numeric-literal* operand is
    arithmetic on every engine (the string is coerced to a number: '10' + 5 = 15,
    '1' + 1 = 2). It must not be rewritten to concatenation. Live-verified."""

    def test_tsql_string_plus_number(self) -> None:
        for target in ("mysql", "oracle", "postgresql"):
            out = _tx(
                _case("challenge_sqlserver.sql", "ts-str-plus-num "), "tsql", target
            )
            body = "\n".join(
                ln for ln in out.splitlines() if not ln.lstrip().startswith("--")
            )
            assert "'10' + 5" in body, body
            assert "||" not in body and "CONCAT" not in body.upper(), body

    def test_oracle_string_plus_number(self) -> None:
        for target in ("mysql", "postgresql", "tsql"):
            out = _tx(
                _case("challenge_oracle.sql", "ora-implicit-arith "), "oracle", target
            )
            assert "'1' + 1" in out, out


class TestMysqlConcatNullPropagates:
    """MySQL CONCAT returns NULL if any argument is NULL; PG/Oracle/T-SQL ignore
    NULL. A MySQL CONCAT with a literal NULL is always NULL — fold it. Only fires
    for a literal NULL, so plain CONCAT (and its roundtrip) is untouched."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql", "tsql"))
    def test_concat_literal_null_is_null(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-concat-null"), "mysql", target)
        assert re.search(r"(?i)SELECT\s+NULL\s+AS\s+r", out), out

    def test_concat_without_null_is_unchanged(self) -> None:
        # Roundtrip-safety: a CONCAT with no NULL literal keeps CONCAT.
        out = _tx("SELECT CONCAT('a', 'b') AS r", "mysql", "postgresql")
        assert "CONCAT('a', 'b')" in out, out

    def test_tsql_source_drops_null_arg(self) -> None:
        # The reverse: T-SQL CONCAT ignores NULL, so the literal NULL is dropped
        # (else MySQL's propagating CONCAT would turn the result NULL).
        out = _tx(_case("challenge_sqlserver.sql", "ts-concat-null"), "tsql", "mysql")
        assert "CONCAT('a', 'b')" in out, out

    def test_pg_source_drops_null_arg(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-concat-null"), "postgresql", "mysql"
        )
        assert "CONCAT('a', 'b')" in out, out


class TestIntegerDivisionSemantics:
    """MySQL/Oracle ``/`` is decimal division (5/2 = 2.5); PG/T-SQL truncate two
    integer operands (5/2 = 2). The emitter forces the source's semantics when
    both operands are known integers."""

    @pytest.mark.parametrize(
        "fixture,source,keyword",
        [
            ("challenge_mysql.sql", "mysql", "my-div"),
            ("challenge_oracle.sql", "oracle", "ora-div"),
        ],
    )
    @pytest.mark.parametrize("target", ("postgresql", "tsql"))
    def test_decimal_div_forced_on_pg_tsql(
        self, fixture: str, source: str, keyword: str, target: str
    ) -> None:
        out = _tx(_case(fixture, keyword), source, target)
        assert "* 1.0 /" in out, out

    def test_pg_intdiv_truncates_on_mysql(self) -> None:
        out = _tx(_case("challenge_postgresql.sql", "pg-intdiv"), "postgresql", "mysql")
        assert "DIV" in out, out

    def test_pg_intdiv_truncates_on_oracle(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-intdiv"), "postgresql", "oracle"
        )
        assert "TRUNC(" in out, out


class TestMysqlCaseInsensitiveSearch:
    """MySQL's default collation is case-insensitive, so LOCATE/INSTR match
    regardless of case (INSTR('aAaA', 'A') = 1); Oracle and PostgreSQL compare
    case-sensitively. The emitter lower-cases both operands there (T-SQL's
    default collation is already case-insensitive, so it is untouched)."""

    @pytest.mark.parametrize("keyword", ("my-instr-case", "my-locate-case"))
    @pytest.mark.parametrize("target", ("oracle", "postgresql"))
    def test_search_lowercased_on_cs_targets(self, keyword: str, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", keyword), "mysql", target)
        assert out.upper().count("LOWER(") >= 2, out

    def test_tsql_not_lowercased(self) -> None:
        # T-SQL is case-insensitive by default — no LOWER needed.
        out = _tx(_case("challenge_mysql.sql", "my-instr-case"), "mysql", "tsql")
        assert "LOWER(" not in out.upper(), out


class TestDatePlusInteger:
    """PostgreSQL/Oracle ``date + n`` adds n days (yielding a date); MySQL reads
    it as a numeric addition (2020-01-01 + 30 = 20200131) and T-SQL rejects it.
    From a PG/Oracle source the emitter spells it as DATE_ADD / DATEADD."""

    def test_pg_date_plus_int_mysql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-date-plus-int"), "postgresql", "mysql"
        )
        assert re.search(r"(?i)DATE_ADD\(.*INTERVAL\s+30\s+DAY\)", out), out

    def test_pg_date_plus_int_tsql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-date-plus-int"), "postgresql", "tsql"
        )
        assert re.search(r"(?i)DATEADD\(\s*DAY\s*,\s*30", out), out

    def test_oracle_date_plus_int_mysql(self) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "ora-date-plus-int2"), "oracle", "mysql"
        )
        assert re.search(r"(?i)DATE_ADD\(.*INTERVAL\s+30\s+DAY\)", out), out


class TestTsqlLoopControl:
    """T-SQL loop body: ``SET @i += 1`` compound assignment, ``BREAK`` and
    ``CONTINUE`` all have to translate to valid PL/SQL, PL/pgSQL and MySQL
    (the procedure would not compile otherwise)."""

    def test_compound_assignment_expands(self) -> None:
        # @i += 1  ->  V_I := V_I + 1 (Oracle), no leftover '= 1'.
        out = _tx(
            _case("challenge_sqlserver.sql", "ts-continue-break"), "tsql", "oracle"
        )
        assert re.search(r"(?i)V_I\s*:=\s*V_I\s*\+\s*\(?1\)?", out), out
        assert ":= =" not in out, out

    @pytest.mark.parametrize(
        "target,brk,cont",
        [
            ("oracle", "EXIT;", "CONTINUE;"),
            ("postgresql", "EXIT;", "CONTINUE;"),
            ("mysql", "LEAVE loop_lbl;", "ITERATE loop_lbl;"),
        ],
    )
    def test_break_continue_map(self, target: str, brk: str, cont: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-continue-break"), "tsql", target)
        body = _exec_lines(out)
        assert brk in body, out
        assert cont in body, out
        assert "BREAK" not in body.upper(), out  # no leftover T-SQL BREAK

    def test_mysql_loop_is_labeled(self) -> None:
        out = _tx(
            _case("challenge_sqlserver.sql", "ts-continue-break"), "tsql", "mysql"
        )
        assert "loop_lbl: WHILE" in out, out


class TestTsqlBitCast:
    """T-SQL ``CAST(x AS BIT)`` maps any non-zero numeric to 1 (0 -> 0, NULL ->
    NULL); other engines keep the value. The emitter normalizes via SIGN(ABS(x))."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql", "mysql"))
    def test_bit_cast_uses_sign_abs(self, target: str) -> None:
        body = _exec_lines(
            _tx(_case("challenge_sqlserver.sql", "ts-cast-bit"), "tsql", target)
        )
        assert re.search(r"(?i)SIGN\s*\(\s*ABS\s*\(", body), body
        assert "AS BIT" not in body.upper(), body


class TestPgDateDifference:
    """PostgreSQL ``DATE - DATE`` is a day count (60); MySQL does a numeric
    subtraction (200) and T-SQL rejects it. The PG date literal parses as
    ``CAST(... AS DATE)``; recognizing that shape lets the emitter spell the
    difference as DATEDIFF on MySQL/T-SQL."""

    def test_mysql_uses_datediff(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-date-diff-days"),
            "postgresql",
            "mysql",
        )
        assert re.search(r"(?i)DATEDIFF\(", out), out

    def test_tsql_uses_datediff_day(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-date-diff-days"), "postgresql", "tsql"
        )
        assert re.search(r"(?i)DATEDIFF\(\s*DAY", out), out


class TestPgUnboundedNumericCastScale:
    """PostgreSQL's unbounded ``numeric`` is arbitrary-precision, but a bare
    DECIMAL cast defaults to scale 0 on MySQL/Oracle/T-SQL and silently
    truncates the fraction (2.675::numeric became 3 before a later ROUND). The
    emitter gives the unbounded cast a scale so the value survives."""

    @pytest.mark.parametrize("keyword", ("pg-round-2675", "pg-round-1005", "pg-fround"))
    @pytest.mark.parametrize("target", ("mysql", "oracle", "tsql"))
    def test_unbounded_numeric_cast_keeps_scale(
        self, keyword: str, target: str
    ) -> None:
        out = _tx(_case("challenge_postgresql.sql", keyword), "postgresql", target)
        assert re.search(r"(?i)AS\s+(?:DECIMAL|NUMERIC|NUMBER)\(38,\s*10\)", out), out


class TestPgSubstringZeroStart:
    """PostgreSQL SUBSTRING(s, start, len) with a start <= 0 counts the
    out-of-range leading positions toward the length (SUBSTRING('abcdef', 0, 3)
    = 'ab'); Oracle clamps 0 to 1 and MySQL returns ''. The emitter rebases to
    start 1 with an adjusted length."""

    @pytest.mark.parametrize("target", ("mysql", "oracle"))
    def test_zero_start_rebased(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-substr-zero"), "postgresql", target
        )
        assert re.search(r"(?i)SUBSTR\('abcdef',\s*1,\s*2\)", out), out

    def test_positive_start_unchanged(self) -> None:
        # A positive start is not rebased — the args stay (2, 3).
        out = _tx("SELECT SUBSTRING('abcdef', 2, 3) AS r", "postgresql", "mysql")
        assert re.search(r"(?i)'abcdef',\s*2,\s*3\)", out), out


class TestTsqlLenTrailingSpaces:
    """T-SQL ``LEN`` excludes trailing spaces (LEN('abc   ') = 3); MySQL
    CHAR_LENGTH and Oracle/PostgreSQL LENGTH count them (6). The emitter trims
    the argument (RTRIM) on non-T-SQL targets to preserve the count."""

    @pytest.mark.parametrize("target", ("mysql", "oracle", "postgresql"))
    def test_len_trims_trailing_on_other_engines(self, target: str) -> None:
        out = _tx(_case("challenge_sqlserver.sql", "ts-len-trailing"), "tsql", target)
        assert "RTRIM(" in out.upper(), out

    def test_len_unchanged_on_tsql(self) -> None:
        out = _tx("SELECT LEN('abc   ') AS r", "tsql", "tsql")
        assert "RTRIM" not in out.upper(), out

    def test_len_counts_trailing_from_oracle(self) -> None:
        # Reverse direction: Oracle/PG LENGTH counts trailing spaces, so on a
        # T-SQL target emit LEN(x + '.') - 1 to preserve the count.
        out = _tx(
            _case("challenge_oracle.sql", "ora-length-trailing"), "oracle", "tsql"
        )
        assert re.search(r"(?i)LEN\(.*\+\s*'\.'\)\s*-\s*1", out), out


class TestPgLeftNegative:
    """PostgreSQL ``LEFT(s, -n)`` returns "all but the last |n|" characters
    (LEFT('abc', -1) = 'ab'); MySQL returns '' for a negative length. The emitter
    rebases to LEFT(s, GREATEST(CHAR_LENGTH(s) + n, 0)) on a MySQL target."""

    def test_negative_length_rebased(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-left-neg"), "postgresql", "mysql"
        )
        assert re.search(
            r"(?i)LEFT\(.*GREATEST\(\s*CHAR_LENGTH\(.*\)\s*\+\s*-1,\s*0\)\)", out
        ), out

    def test_positive_length_unchanged(self) -> None:
        # A positive length is not rebased — LEFT('abc', 2) stays as-is.
        out = _tx("SELECT LEFT('abc', 2) AS r", "postgresql", "mysql")
        assert "GREATEST" not in out.upper(), out


class TestTsqlAvgIntegerPromotion:
    """T-SQL ``AVG`` returns the input type, so ``AVG`` over an integer column
    truncates (AVG of 1, 2 = 1); MySQL/Oracle/PostgreSQL always average as a
    decimal (1.5). The emitter promotes the argument (``AVG((x) * 1.0)``)."""

    @pytest.mark.parametrize(
        "fixture,source,keyword",
        [
            ("challenge_mysql.sql", "mysql", "my-avg-int"),
            ("challenge_postgresql.sql", "postgresql", "pg-avg-int"),
        ],
    )
    def test_avg_promoted_to_decimal_on_tsql(
        self, fixture: str, source: str, keyword: str
    ) -> None:
        out = _tx(_case(fixture, keyword), source, "tsql")
        assert re.search(r"(?i)AVG\(\s*\(.*\)\s*\*\s*1\.0\s*\)", out), out

    def test_avg_not_promoted_on_pg(self) -> None:
        # The promotion is T-SQL-only; PG already averages as decimal.
        out = _tx(_case("challenge_mysql.sql", "my-avg-int"), "mysql", "postgresql")
        assert "* 1.0" not in out, out


class TestLogArgumentOrder:
    """PostgreSQL ``LOG(base, x)`` takes the base first; T-SQL ``LOG(x, base)``
    takes it last, so the two arguments must be swapped (LOG(2, 8) = 3)."""

    def test_pg_log_two_arg_swaps_for_tsql(self) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-log-2arg"), "postgresql", "tsql"
        )
        assert re.search(r"(?i)LOG\(\s*8\s*,\s*2\s*\)", out), out


class TestNullOrderingEmulation:
    """Oracle/PostgreSQL sort NULLs HIGH by default (LAST ascending); MySQL and
    T-SQL sort them LOW and lack a NULLS FIRST/LAST keyword. The emitter restores
    the source order with a leading ``CASE WHEN col IS NULL`` priority key."""

    @pytest.mark.parametrize("target", ("mysql", "tsql"))
    def test_oracle_nulls_last_default_emulated(self, target: str) -> None:
        out = _tx(
            _case("challenge_oracle.sql", "ora-order-nulls-default"), "oracle", target
        )
        assert re.search(r"(?i)CASE WHEN .*IS NULL THEN 1 ELSE 0 END", out), out

    @pytest.mark.parametrize("target", ("mysql", "tsql"))
    def test_pg_nulls_last_default_emulated(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "pg-order-nulls-default"),
            "postgresql",
            target,
        )
        assert re.search(r"(?i)CASE WHEN .*IS NULL THEN 1 ELSE 0 END", out), out

    @pytest.mark.parametrize("target", ("mysql", "tsql"))
    def test_pg_group_by_nulls_last_emulated(self, target: str) -> None:
        out = _tx(
            _case("challenge_postgresql.sql", "po-group-null"), "postgresql", target
        )
        assert re.search(r"(?i)CASE WHEN .*IS NULL THEN 1 ELSE 0 END", out), out

    def test_tsql_distinct_omits_key_to_stay_valid(self) -> None:
        # T-SQL forbids an ORDER BY expression outside the select list under
        # DISTINCT, so the null-priority key is skipped there (valid, divergent).
        out = _tx(
            _case("challenge_postgresql.sql", "po-distinct-null"), "postgresql", "tsql"
        )
        assert "IS NULL THEN" not in out.upper(), out

    def test_mysql_distinct_keeps_key(self) -> None:
        # MySQL allows a non-selected ORDER BY expression under DISTINCT, so the
        # emulation still applies there.
        out = _tx(
            _case("challenge_postgresql.sql", "po-distinct-null"), "postgresql", "mysql"
        )
        assert re.search(r"(?i)CASE WHEN .*IS NULL THEN 1 ELSE 0 END", out), out

    def test_window_order_by_untouched(self) -> None:
        # A window ORDER BY must NOT get a null-priority key (it would change the
        # frame's peer groups).
        out = _tx("SELECT ROW_NUMBER() OVER (ORDER BY x) FROM t", "postgresql", "mysql")
        assert "IS NULL THEN" not in out.upper(), out


class TestMysqlReplaceNullPropagates:
    """MySQL REPLACE propagates NULL — REPLACE(str, NULL, x) is NULL — while
    Oracle ignores a NULL search/replace and returns the subject unchanged. A
    literal-NULL arg makes the MySQL result NULL; fold it. Only fires for a
    literal NULL, so plain REPLACE (and its roundtrip) is untouched."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql", "tsql"))
    def test_replace_literal_null_is_null(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-replace-null2"), "mysql", target)
        # The REPLACE call collapsed to a bare NULL (no REPLACE call survives).
        assert "REPLACE(" not in out.upper(), out
        assert re.search(r"(?i)\bNULL\s+IS\s+NULL\b", out), out

    def test_replace_without_null_is_unchanged(self) -> None:
        out = _tx("SELECT REPLACE('abc', 'a', 'x') AS r", "mysql", "oracle")
        assert "REPLACE('abc', 'a', 'x')" in out, out


class TestMysqlConcatNumBool:
    """MySQL CONCAT stringifies numbers, floats and booleans (5->'5', TRUE->'1')
    and propagates NULL. Cured by the CONCAT boolean->int and NULL-fold handlers:
    CONCAT('x',5), CONCAT('x',5.5), CONCAT('x',TRUE)->CONCAT('x',1),
    CONCAT('x',NULL)->NULL all match. Live-verified on all three."""

    @pytest.mark.parametrize("target", ("oracle", "postgresql", "tsql"))
    def test_concat_num_bool_null(self, target: str) -> None:
        out = _tx(_case("challenge_mysql.sql", "my-fconcatnum"), "mysql", target)
        assert "CONCAT('x', 1)" in out and "NULL" in out, out
